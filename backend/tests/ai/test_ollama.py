"""Ollama (IA locale) : API native, contexte fixé, gratuit ; « Tester » de l'espace parent."""

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from app.ai.check import check
from app.ai.factory import AiChoice, build_llm
from app.ai.ports import AIError, AIInvalidOutput, PageImage, Prompt, Stage
from app.ai.pricing import run_cost
from app.ai.providers.ollama import OllamaProvider
from app.config import Settings

PROMPT = Prompt("ocr", "v9", "Lis la page.")
MODELS: dict[Stage, str] = {s: "qwen2.5vl:7b" for s in ("ocr", "analysis", "material", "evaluation")}


class Page(BaseModel):
    text: str


def ollama(handler: Callable[[httpx.Request], httpx.Response]) -> OllamaProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OllamaProvider("http://host.docker.internal:11434/", MODELS, num_ctx=16384, client=client)


async def test_native_chat_with_images_and_context() -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content) | {"_url": str(request.url)})
        return httpx.Response(
            200,
            json={
                "model": "qwen2.5vl:7b",
                "message": {"role": "assistant", "content": '{"text": "Les fractions"}'},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 900,
                "eval_count": 40,
            },
        )

    llm = ollama(handler)
    result = await llm.structured(
        prompt=PROMPT, input="Page 1", schema=Page, images=(PageImage(b"\xff\xd8jpeg", "image/jpeg"),)
    )
    assert result.output.text == "Les fractions"
    assert (result.usage.provider, result.usage.model) == ("ollama", "ollama/qwen2.5vl:7b")
    assert run_cost(result.usage.model, 900, 40) == 0.0  # gratuit : le plafond ne bouge pas
    (body,) = sent
    assert body["_url"] == "http://host.docker.internal:11434/api/chat"
    assert body["stream"] is False and body["options"]["num_ctx"] == 16384
    assert body["format"]["title"] == "Page"
    assert body["messages"][1]["images"] == ["/9hqcGVn"]
    assert '"text"' in body["messages"][0]["content"]  # schéma rappelé dans les consignes


@pytest.mark.parametrize(
    ("response", "error", "message"),
    [
        (httpx.Response(404, json={"error": "model not found"}), AIError, "ollama pull qwen2.5vl:7b"),
        (httpx.Response(500, text="boom"), AIError, "Ollama 500"),
        (
            httpx.Response(200, json={"message": {"content": "{"}, "done_reason": "length"}),
            AIInvalidOutput,
            "NUM_CTX",
        ),
        (
            httpx.Response(200, json={"message": {"content": "{}"}, "done_reason": "stop"}),
            AIInvalidOutput,
            "schéma",
        ),
    ],
)
async def test_errors(response: httpx.Response, error: type[Exception], message: str) -> None:
    with pytest.raises(error, match=message):
        await ollama(lambda request: response).structured(prompt=PROMPT, input="x", schema=Page)


async def test_ollama_not_running() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(AIError, match="est-il lancé"):
        await ollama(handler).structured(prompt=PROMPT, input="x", schema=Page)


def test_factory_builds_ollama_without_key() -> None:
    llm = build_llm(Settings(ai_provider="ollama", ollama_base_url="http://pc:11434"))
    assert isinstance(llm, OllamaProvider) and llm.base_url == "http://pc:11434"
    assert llm.model_for("evaluation") == "qwen2.5vl:7b"
    chosen = build_llm(Settings(), AiChoice("ollama", "gemma3:12b", "http://autre:11434"))
    assert isinstance(chosen, OllamaProvider)
    assert (chosen.base_url, chosen.model_for("ocr")) == ("http://autre:11434", "gemma3:12b")


def client_for(routes: dict[str, httpx.Response]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return routes.get(str(request.url), httpx.Response(404))

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_check_ollama_models() -> None:
    tags = "http://localhost:11434/api/tags"
    installed = client_for(
        {tags: httpx.Response(200, json={"models": [{"name": "qwen2.5vl:7b"}, {"name": "llama3:8b"}]})}
    )
    ok = await check(AiChoice("ollama"), Settings(), installed)
    assert ok.ok and ok.models == ["llama3:8b", "qwen2.5vl:7b"]
    missing = await check(AiChoice("ollama", "gemma3:12b"), Settings(), installed)
    assert not missing.ok and "ollama pull gemma3:12b" in missing.message
    empty = await check(
        AiChoice("ollama"), Settings(), client_for({tags: httpx.Response(200, json={"models": []})})
    )
    assert not empty.ok and "aucun modèle" in empty.message


async def test_check_api_keys() -> None:
    mistral = client_for(
        {
            "https://api.mistral.ai/v1/models": httpx.Response(
                200, json={"data": [{"id": "mistral-medium-latest"}]}
            )
        }
    )
    ok = await check(AiChoice("mistral", api_key="k"), Settings(), mistral)
    assert ok.ok and ok.models == ["mistral-medium-latest"]
    refused = client_for({"https://api.openai.com/v1/models": httpx.Response(401)})
    result = await check(AiChoice("openai", api_key="bad"), Settings(), refused)
    assert not result.ok and "Clé refusée" in result.message
    claude = client_for(
        {"https://api.anthropic.com/v1/models": httpx.Response(200, json={"data": [{"id": "claude-opus-5"}]})}
    )
    assert (await check(AiChoice("claude", api_key="sk-ant-x"), Settings(), claude)).models == [
        "claude-opus-5"
    ]
    assert (await check(AiChoice("fake"), Settings())).ok
