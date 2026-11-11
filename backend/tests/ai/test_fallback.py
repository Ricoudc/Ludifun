"""Repli sur une autre IA (CDC §147)."""

import httpx
import pytest
from pydantic import BaseModel

from app.ai.fallback import FallbackLLM
from app.ai.ports import AIError, AIInvalidOutput, LLMResult, PageImage, Prompt, Stage, Usage
from app.ai.providers.ollama import OllamaProvider

PROMPT = Prompt("analysis", "v9", "Analyse.")


class Out(BaseModel):
    ok: bool


class Stub:
    def __init__(self, name: str, error: AIError | None = None) -> None:
        self.name = name
        self.error = error
        self.calls = 0

    def model_for(self, stage: Stage) -> str:
        return f"{self.name}-model"

    async def structured[T: BaseModel](
        self, *, prompt: Prompt, input: str, schema: type[T], images: tuple[PageImage, ...] = ()
    ) -> LLMResult[T]:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return LLMResult(schema.model_validate({"ok": True}), Usage(self.name, f"{self.name}-model", 1, 1, 5))


async def test_the_next_ai_answers_when_the_first_is_down() -> None:
    first, second = Stub("ollama", AIError("Ollama n'a pas répondu en 15 min")), Stub("gemini")
    llm = FallbackLLM([first, second])
    assert llm.name == "ollama" and llm.model_for("ocr") == "ollama-model"
    result = await llm.structured(prompt=PROMPT, input="x", schema=Out)
    assert result.usage.provider == "gemini"
    assert result.usage.fallback_from == "ollama : Ollama n'a pas répondu en 15 min"


async def test_text_only_ollama_is_skipped_for_image_requests() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/show"
        return httpx.Response(200, json={"capabilities": ["completion"]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    local = OllamaProvider("http://pc:11434", {"ocr": "mistral:7b"}, client=client)
    cloud = Stub("claude")
    result = await FallbackLLM([local, cloud]).structured(
        prompt=PROMPT,
        input="Transcris cette photo",
        schema=Out,
        images=(PageImage(b"photo", "image/png"),),
    )
    await client.aclose()

    assert cloud.calls == 1
    assert result.usage.provider == "claude"
    assert "ne sait pas lire les images" in (result.usage.fallback_from or "")


async def test_no_fallback_for_an_answer_out_of_format() -> None:
    first, second = Stub("ollama", AIInvalidOutput("réponse hors schéma")), Stub("gemini")
    with pytest.raises(AIInvalidOutput):
        await FallbackLLM([first, second]).structured(prompt=PROMPT, input="x", schema=Out)
    assert second.calls == 0


async def test_all_down() -> None:
    llm = FallbackLLM([Stub("ollama", AIError("injoignable")), Stub("gemini", AIError("API gemini 429"))])
    with pytest.raises(AIError, match="ollama : injoignable ; gemini : API gemini 429"):
        await llm.structured(prompt=PROMPT, input="x", schema=Out)


async def test_a_single_ai_answers_normally() -> None:
    result = await FallbackLLM([Stub("claude")]).structured(prompt=PROMPT, input="x", schema=Out)
    assert result.usage.fallback_from is None
