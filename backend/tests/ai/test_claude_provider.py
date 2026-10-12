"""L'adaptateur Claude, testé contre un faux serveur HTTP (aucun appel réseau réel)."""

import json
from typing import Any

import anthropic
import httpx2
import pytest

from app.ai.ocr.vision_llm import VisionLLMOcr
from app.ai.ports import AIError, AIInvalidOutput, AIRefused, PageImage, Prompt
from app.ai.providers.claude import FALLBACK_BETA, ClaudeProvider
from app.ai.schemas import AnalysisOutput, OcrResult

OCR_JSON = {
    "pages": [{"index": 0, "quality": "good", "text": "La Révolution française"}],
    "language": "fr",
    "warnings": [],
}


def message(
    output: dict[str, Any] | str, stop_reason: str = "end_turn", model: str = "claude-opus-5"
) -> dict[str, Any]:
    text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 1234, "output_tokens": 56},
    }


class FakeApi:
    """Capture les requêtes et renvoie une réponse préparée."""

    def __init__(self, status: int = 200, body: dict[str, Any] | None = None) -> None:
        self.status, self.body = status, body or message(OCR_JSON)
        self.requests: list[httpx2.Request] = []

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return httpx2.Response(self.status, json=self.body)

    def provider(self) -> ClaudeProvider:
        client = anthropic.AsyncAnthropic(
            api_key="test-key",
            max_retries=0,
            http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(self.handler)),
        )
        return ClaudeProvider(
            models={"ocr": "claude-ocr-model", "analysis": "claude-opus-5", "material": "claude-opus-5"},
            efforts={"ocr": "low", "analysis": "high", "material": "medium"},
            client=client,
        )

    @property
    def sent(self) -> dict[str, Any]:
        body: dict[str, Any] = json.loads(self.requests[-1].content)
        return body


async def test_request_shape_for_ocr_with_images() -> None:
    api = FakeApi()
    ocr = VisionLLMOcr(api.provider())
    result = await ocr.extract(
        (PageImage(b"\xff\xd8\xffjpeg", "image/jpeg"), PageImage(b"\x89PNG", "image/png"))
    )

    body = api.sent
    assert body["model"] == "claude-ocr-model"
    assert body["thinking"] == {"type": "adaptive"}
    assert body["output_config"]["effort"] == "low"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["fallbacks"] == "default"
    assert FALLBACK_BETA in api.requests[-1].headers["anthropic-beta"]
    # Prompt système fixe, mis en cache ; les images dans le message.
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert body["system"][0]["text"] == Prompt.load("ocr").text
    content = body["messages"][0]["content"]
    images = [c for c in content if c["type"] == "image"]
    assert [i["source"]["media_type"] for i in images] == ["image/jpeg", "image/png"]
    assert content[-1]["type"] == "text"

    # Une page par image : la page oubliée par le modèle est marquée illisible.
    assert [p.quality for p in result.output.pages] == ["good", "unreadable"]
    assert result.usage.input_tokens == 1234
    assert result.usage.model == "claude-opus-5"


async def test_structured_output_is_parsed() -> None:
    analysis = {
        "is_lesson": False,
        "lesson": None,
        "knowledge": [],
        "skills": [],
        "warnings": ["photo de chat"],
    }
    api = FakeApi(body=message(analysis))
    result = await api.provider().structured(
        prompt=Prompt.load("analysis"), input="<lecon>…</lecon>", schema=AnalysisOutput
    )
    assert isinstance(result.output, AnalysisOutput)
    assert result.output.warnings == ["photo de chat"]
    assert api.sent["output_config"]["effort"] == "high"
    assert "images" not in json.dumps(api.sent["messages"])


@pytest.mark.parametrize(
    "body, error",
    [
        (message(OCR_JSON, stop_reason="refusal"), AIRefused),
        (message(OCR_JSON, stop_reason="max_tokens"), AIInvalidOutput),
        (message("pas du JSON"), AIInvalidOutput),
        (message({"pages": "oups"}), AIInvalidOutput),
    ],
)
async def test_bad_responses(body: dict[str, Any], error: type[Exception]) -> None:
    api = FakeApi(body=body)
    with pytest.raises(error):
        await api.provider().structured(prompt=Prompt.load("ocr"), input="…", schema=OcrResult)


@pytest.mark.parametrize("status", [400, 401, 429, 500, 529])
async def test_http_errors_become_ai_errors(status: int) -> None:
    api = FakeApi(status=status, body={"type": "error", "error": {"type": "api_error", "message": "boom"}})
    with pytest.raises(AIError) as info:
        await api.provider().structured(prompt=Prompt.load("ocr"), input="…", schema=OcrResult)
    assert type(info.value) is AIError
    assert str(status) in str(info.value)


async def test_a_schema_too_large_for_the_grammar_falls_back_to_validated_json() -> None:
    """Claude refuse parfois le schéma de l'analyse (« compiled grammar is too large ») : la
    requête repart sans sortie contrainte, schéma dans les consignes, réponse validée ici."""
    analysis = {"is_lesson": False, "lesson": None, "knowledge": [], "skills": [], "warnings": ["chat"]}
    too_large = {
        "type": "error",
        "error": {
            "type": "invalid_request_error",
            "message": "The compiled grammar is too large, which would cause performance issues.",
        },
    }
    api = FakeApi()
    replies = [httpx2.Response(400, json=too_large), httpx2.Response(200, json=message(analysis))]

    def handler(request: httpx2.Request) -> httpx2.Response:
        api.requests.append(request)
        return replies.pop(0)

    api.handler = handler  # type: ignore[method-assign]
    result = await api.provider().structured(
        prompt=Prompt.load("analysis"), input="<lecon>…</lecon>", schema=AnalysisOutput
    )
    assert result.output.warnings == ["chat"]
    first, second = (json.loads(r.content) for r in api.requests)
    assert first["output_config"]["format"]["type"] == "json_schema"
    assert "format" not in second["output_config"]
    assert "# Format de la réponse" in second["system"][0]["text"]

    # Une autre erreur 400 n'est pas relancée.
    other = FakeApi(
        status=400, body={"type": "error", "error": {"type": "invalid_request_error", "message": "x"}}
    )
    with pytest.raises(AIError, match="400"):
        await other.provider().structured(prompt=Prompt.load("ocr"), input="…", schema=OcrResult)
    assert len(other.requests) == 1
