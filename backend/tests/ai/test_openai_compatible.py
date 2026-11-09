"""Fournisseurs compatibles OpenAI (ChatGPT, Gemini, Mistral, Groq, Grok, Azure/Copilot…),
essayés contre un faux serveur HTTP : aucune clé ni appel réel."""

import json
import re
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, ValidationError

from app.ai.factory import AiConfigError, build_llm, stage_models
from app.ai.ports import AIError, AIInvalidOutput, AIRefused, PageImage, Prompt, Stage, schema_error
from app.ai.providers.claude import ClaudeProvider
from app.ai.providers.fake import FakeProvider
from app.ai.providers.openai_compatible import MAX_RATE_RETRIES, OpenAICompatibleProvider, rate_limit_wait
from app.config import Settings

PROMPT = Prompt("analysis", "v9", "Analyse la leçon.")


class Answer(BaseModel):
    title: str
    count: int


def reply(content: str | None, *, finish: str = "stop", refusal: str | None = None) -> dict[str, Any]:
    return {
        "model": "gpt-5-2026",
        "choices": [{"message": {"content": content, "refusal": refusal}, "finish_reason": finish}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 30},
    }


Handler = Callable[[dict[str, Any], int], httpx.Response]


def provider(handler: Handler) -> tuple[OpenAICompatibleProvider, list[dict[str, Any]]]:
    sent: list[dict[str, Any]] = []

    def record(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append(body | {"_auth": request.headers["Authorization"], "_url": str(request.url)})
        return handler(body, len(sent))

    client = httpx.AsyncClient(transport=httpx.MockTransport(record))
    models: dict[Stage, str] = {
        "ocr": "gpt-5",
        "analysis": "gpt-5",
        "material": "gpt-5",
        "evaluation": "gpt-5-mini",
    }
    return OpenAICompatibleProvider("openai", "https://api.example/v1/", "sk-test", models, client), sent


async def test_structured_output_with_images() -> None:
    llm, sent = provider(
        lambda body, n: httpx.Response(200, json=reply('{"title": "Fractions", "count": 3}'))
    )
    image = PageImage(b"\xff\xd8photo", "image/jpeg")
    result = await llm.structured(prompt=PROMPT, input="<lecon>…</lecon>", schema=Answer, images=(image,))

    assert result.output == Answer(title="Fractions", count=3)
    assert (result.usage.provider, result.usage.model) == ("openai", "gpt-5-2026")
    assert (result.usage.input_tokens, result.usage.output_tokens) == (120, 30)
    (body,) = sent
    assert body["_url"] == "https://api.example/v1/chat/completions"
    assert body["_auth"] == "Bearer sk-test" and body["model"] == "gpt-5"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"]["title"] == "Answer"
    system, user = body["messages"]
    assert system["content"].startswith("Analyse la leçon.") and '"count"' in system["content"]
    assert user["content"][0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert user["content"][-1] == {"type": "text", "text": "<lecon>…</lecon>"}


async def test_falls_back_to_json_object_and_strips_fences() -> None:
    def handler(body: dict[str, Any], n: int) -> httpx.Response:
        if body["response_format"]["type"] == "json_schema":
            return httpx.Response(
                400, json={"error": {"message": "response_format json_schema not supported"}}
            )
        return httpx.Response(200, json=reply('```json\n{"title": "Eau", "count": 1}\n```'))

    llm, sent = provider(handler)
    result = await llm.structured(prompt=PROMPT, input="texte", schema=Answer)
    assert result.output.title == "Eau"
    assert [b["response_format"]["type"] for b in sent] == ["json_schema", "json_object"]
    assert sent[0]["messages"][1]["content"] == "texte"  # sans image : texte simple


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(200, json=reply(None, refusal="Je ne peux pas.")), AIRefused),
        (httpx.Response(200, json=reply('{"title": "x"', finish="length")), AIInvalidOutput),
        (httpx.Response(200, json=reply('{"title": "x"}')), AIInvalidOutput),  # hors schéma
        (httpx.Response(200, json=reply("pas du JSON")), AIInvalidOutput),
        (httpx.Response(200, json={"choices": []}), AIInvalidOutput),
        (httpx.Response(401, json={"error": {"message": "Invalid API key"}}), AIError),
        (httpx.Response(429, json={"error": {"message": "quota"}}), AIError),
    ],
)
async def test_errors(response: httpx.Response, error: type[Exception]) -> None:
    llm, _ = provider(lambda body, n: response)
    with pytest.raises(error):
        await llm.structured(prompt=PROMPT, input="texte", schema=Answer)


async def test_network_error() -> None:
    def handler(body: dict[str, Any], n: int) -> httpx.Response:
        raise httpx.ConnectError("injoignable")

    llm, _ = provider(handler)
    with pytest.raises(AIError, match="connexion impossible"):
        await llm.structured(prompt=PROMPT, input="texte", schema=Answer)


@pytest.mark.parametrize(
    ("name", "key_env", "url"),
    [
        ("openai", "OPENAI_API_KEY", "https://api.openai.com/v1"),
        ("gemini", "GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai"),
        ("mistral", "MISTRAL_API_KEY", "https://api.mistral.ai/v1"),
        ("groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1"),
        ("xai", "XAI_API_KEY", "https://api.x.ai/v1"),
    ],
)
def test_known_providers(name: str, key_env: str, url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(key_env, "cle-de-test")
    llm = build_llm(Settings(ai_provider=name))
    assert isinstance(llm, OpenAICompatibleProvider)
    assert (llm.name, llm.base_url) == (name, url)
    assert llm._headers == {"Authorization": "Bearer cle-de-test"}
    assert all(llm.model_for(stage) for stage in ("ocr", "analysis", "material", "evaluation"))


def test_models_can_be_chosen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    one = stage_models(Settings(ai_provider="mistral", ai_model="pixtral-large-latest"))
    assert set(one.values()) == {"pixtral-large-latest"}
    mixed = stage_models(Settings(ai_provider="mistral", ai_evaluation_model="mistral-small-latest"))
    assert mixed["evaluation"] == "mistral-small-latest" and mixed["ocr"] == "mistral-medium-latest"
    assert stage_models(Settings())["evaluation"] == "claude-sonnet-5"  # Claude par défaut


def test_compatible_service_for_copilot_azure_or_ollama() -> None:
    with pytest.raises(AiConfigError, match="modèle manquant"):
        build_llm(Settings(ai_provider="compatible", ai_base_url="https://x.example/openai/v1"))
    with pytest.raises(AiConfigError, match="adresse manquante"):
        build_llm(Settings(ai_provider="compatible", ai_model="gpt-5"))
    llm = build_llm(
        Settings(
            ai_provider="compatible",
            ai_base_url="https://ma-ressource.openai.azure.com/openai/v1",
            ai_api_key="azure-key",
            ai_model="gpt-5",
        )
    )
    assert isinstance(llm, OpenAICompatibleProvider)
    assert llm.base_url == "https://ma-ressource.openai.azure.com/openai/v1"
    assert llm._headers["Authorization"] == "Bearer azure-key"


def test_claude_and_fake_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert isinstance(build_llm(Settings()), ClaudeProvider)
    assert isinstance(build_llm(Settings(ai_provider="fake")), FakeProvider)


@pytest.mark.parametrize(
    ("headers", "message", "seconds"),
    [
        ({"retry-after": "7"}, "", 7.0),
        (
            {},
            "Rate limit reached for model `qwen` on tokens per minute (TPM). Please try again in 2.15s.",
            2.15,
        ),
        ({}, "Please try again in 1m26.4s.", 86.4),
        ({}, "Please try again in 360ms.", 0.36),
        ({}, "quota", None),
    ],
)
def test_rate_limit_wait(headers: dict[str, str], message: str, seconds: float | None) -> None:
    response = httpx.Response(429, headers=headers, json={"error": {"message": message}})
    assert (
        rate_limit_wait(response) == pytest.approx(seconds) if seconds else rate_limit_wait(response) is None
    )


def limited(message: str) -> httpx.Response:
    return httpx.Response(
        429, json={"error": {"message": message, "type": "tokens", "code": "rate_limit_exceeded"}}
    )


async def test_per_minute_limit_waits_then_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Groq gratuit : « trop de jetons par minute » → on attend le délai annoncé, puis on réessaie."""
    waits: list[float] = []

    async def no_wait(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr("app.ai.providers.openai_compatible._sleep", no_wait)
    llm, sent = provider(
        lambda body, n: (
            limited("Please try again in 7.5s.")
            if n < 3
            else httpx.Response(200, json=reply('{"title": "Les fractions", "count": 2}'))
        )
    )
    result = await llm.structured(prompt=PROMPT, input="texte", schema=Answer)
    assert result.output.title == "Les fractions" and len(sent) == 3
    assert waits == [8.0, 8.0]  # le délai annoncé, et une demi-seconde de marge


async def test_daily_limit_and_endless_refusals_do_not_wait_forever(monkeypatch: pytest.MonkeyPatch) -> None:
    waits: list[float] = []

    async def no_wait(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr("app.ai.providers.openai_compatible._sleep", no_wait)
    daily, sent = provider(lambda body, n: limited("tokens per day (TPD). Please try again in 7m12s."))
    with pytest.raises(AIError, match="429"):
        await daily.structured(prompt=PROMPT, input="texte", schema=Answer)
    assert len(sent) == 1 and waits == []  # quota du jour : pas d'attente
    stuck, sent = provider(lambda body, n: limited("Please try again in 1s."))
    with pytest.raises(AIError, match="429"):
        await stuck.structured(prompt=PROMPT, input="texte", schema=Answer)
    assert len(sent) == MAX_RATE_RETRIES + 1 and len(waits) == MAX_RATE_RETRIES


async def test_an_error_never_carries_what_the_model_wrote() -> None:
    """Le service joint parfois sa génération ratée (texte tiré de la leçon) : elle ne sort pas."""
    refused = httpx.Response(
        400,
        json={
            "error": {
                "message": "Failed to generate JSON. See 'failed_generation' for more details.",
                "type": "invalid_request_error",
                "code": "json_validate_failed",
                "failed_generation": '{"title": "Louis XVI convoque les États généraux',
            }
        },
    )
    llm, _ = provider(lambda body, n: refused)
    with pytest.raises(AIError) as caught:
        await llm.structured(prompt=PROMPT, input="texte", schema=Answer)
    message = str(caught.value)
    assert "400" in message and "json_validate_failed" in message and "Failed to generate JSON" in message
    assert "Louis" not in message and "États" not in message
    # Une page d'erreur (pas du JSON) ou une erreur sans message restent lisibles.
    for response, expected in (
        (httpx.Response(502, text="<html>Bad Gateway</html>"), "Bad Gateway"),
        (httpx.Response(500, json={"error": "panne"}), "panne"),
        (httpx.Response(500, json={"detail": {"lesson": "Louis XVI"}}), "erreur sans message"),
    ):

        def reply_with(body: dict[str, Any], n: int, response: httpx.Response = response) -> httpx.Response:
            return response

        llm, _ = provider(reply_with)
        with pytest.raises(AIError, match=expected) as caught:
            await llm.structured(prompt=PROMPT, input="texte", schema=Answer)
        assert "Louis" not in str(caught.value)


def test_an_out_of_schema_answer_is_described_without_its_text() -> None:
    """Le message d'une sortie hors schéma dit où et pourquoi, jamais ce que le modèle a écrit."""

    class Fiche(BaseModel):
        titre: str
        notes: dict[str, int]

    try:
        Fiche.model_validate({"titre": {"texte": "Louis XVI"}, "notes": {"États généraux": "beaucoup"}})
    except ValidationError as exc:
        message = str(schema_error(exc))
    assert message.startswith("réponse hors schéma : 2 erreur(s)")
    assert "titre : string_type" in message and "notes.… : int_parsing" in message
    assert not {"Louis", "États", "beaucoup", "input_value"} & set(re.findall(r"\w+", message))
    assert str(schema_error(json.JSONDecodeError("Louis XVI", "Louis XVI", 0))) == (
        "réponse hors schéma : JSON illisible"
    )
