"""Ollama (IA locale) : API native, contexte fixé, gratuit ; « Tester » de l'espace parent."""

import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from app.ai.check import check, probe_llm
from app.ai.factory import AiChoice, build_llm
from app.ai.ports import AIContextFull, AIError, AIInvalidOutput, PageImage, Prompt, Stage
from app.ai.pricing import run_cost
from app.ai.providers.ollama import MAX_OUTPUT, OllamaProvider
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
    # Une réponse qui tourne en boucle est coupée : elle ne bloque pas les leçons suivantes.
    assert body["options"]["num_predict"] == MAX_OUTPUT[PROMPT.stage]
    assert body["keep_alive"] == "30m"  # pas de rechargement d'une minute à chaque leçon
    assert body["format"]["title"] == "Page"
    assert body["messages"][1]["images"] == ["/9hqcGVn"]
    assert '"text"' in body["messages"][0]["content"]  # schéma rappelé dans les consignes


async def test_material_schema_is_enforced_not_repeated() -> None:
    """Préparation des exercices : le schéma (≈ 2 000 jetons) n'est plus recopié dans les
    consignes, Ollama l'impose avec `format` ; la réponse a ainsi la place de finir."""
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": '{"text": "ok"}'}, "done_reason": "stop"})

    await ollama(handler).structured(prompt=Prompt("material", "v8", "Prépare."), input="x", schema=Page)
    (body,) = sent
    assert body["format"]["title"] == "Page"
    assert '"properties"' not in body["messages"][0]["content"]
    assert "JSON" in body["messages"][0]["content"]


async def test_truncation_says_how_full_the_context_was() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {"content": "{"},
                "done_reason": "length",
                "prompt_eval_count": 7000,
                "eval_count": 1192,
            },
        )

    with pytest.raises(AIContextFull, match=r"7000 jetons.*1192 jetons.*16384"):
        await ollama(handler).structured(prompt=PROMPT, input="x", schema=Page)


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
            httpx.Response(
                200, json={"message": {"content": "{"}, "done_reason": "length", "eval_count": 2500}
            ),
            AIInvalidOutput,
            "tourné en boucle",
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


def test_the_server_model_does_not_leak_into_another_provider() -> None:
    """Serveur réglé sur Gemini (.env), famille sur Ollama sans modèle : le modèle conseillé
    d'Ollama, pas « gemini-2.5-pro » (qu'Ollama ne connaît pas)."""
    server = Settings(ai_provider="gemini", ai_model="gemini-2.5-pro", ai_ocr_model="gemini-2.5-flash")
    family = build_llm(server, AiChoice("ollama"))
    assert isinstance(family, OllamaProvider) and family.model_for("ocr") == "qwen2.5vl:7b"
    assert family.model_for("material") == "qwen2.5vl:7b"
    # Même fournisseur que le serveur : ses modèles restent la valeur par défaut.
    same = Settings(ai_provider="ollama", ai_model="gemma3:12b")
    assert build_llm(same, AiChoice("ollama")).model_for("ocr") == "gemma3:12b"


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


async def test_check_vision_and_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    tags = httpx.Response(200, json={"models": [{"name": "llama3:8b"}, {"name": "qwen2.5vl:7b"}]})

    def ollama_server(capabilities: list[str] | None) -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/tags":
                return tags
            assert json.loads(request.content)["model"] in ("llama3:8b", "qwen2.5vl:7b")
            return httpx.Response(200, json={} if capabilities is None else {"capabilities": capabilities})

        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    blind = await check(AiChoice("ollama", "llama3:8b"), Settings(), ollama_server(["completion"]))
    assert not blind.ok and "ne sait pas lire les images" in blind.message

    calls: list[AiChoice] = []

    async def works(choice: AiChoice) -> None:
        calls.append(choice)

    seeing = await check(AiChoice("ollama"), Settings(), ollama_server(["completion", "vision"]), works)
    assert seeing.ok and "Demande d'essai réussie" in seeing.message and calls == [AiChoice("ollama")]
    old_ollama = await check(AiChoice("ollama"), Settings(), ollama_server(None), works)
    assert old_ollama.ok  # version sans « capabilities » : on ne bloque pas

    async def broken(choice: AiChoice) -> None:
        raise AIError("modèle Ollama absent")

    failed = await check(AiChoice("ollama"), Settings(), ollama_server(["vision"]), broken)
    assert not failed.ok and "la demande d'essai a échoué : modèle Ollama absent" in failed.message

    async def slow(choice: AiChoice) -> None:
        await asyncio.sleep(1)

    monkeypatch.setattr("app.ai.check.PROBE_TIMEOUT_S", 0.01)
    late = await check(AiChoice("ollama"), Settings(), ollama_server(["vision"]), slow)
    assert not late.ok and "n'a pas abouti" in late.message

    # Service injoignable : pas de demande d'essai.
    calls.clear()

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    down = await check(
        AiChoice("ollama"), Settings(), httpx.AsyncClient(transport=httpx.MockTransport(refuse)), works
    )
    assert not down.ok and calls == []


async def test_probe_uses_the_main_model() -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": '{"ok": true}'}, "done_reason": "stop"})

    await probe_llm(ollama(handler))
    assert sent[0]["model"] == "qwen2.5vl:7b" and sent[0]["format"]["title"] == "ProbeOut"


async def test_large_photos_are_shrunk_before_sending() -> None:
    """Une photo de 2000 px est réduite à 1344 px : l'IA du PC la lit bien plus vite."""
    import base64
    import io

    from PIL import Image

    from app.ai.images import shrink
    from app.ai.providers.ollama import MAX_IMAGE_SIDE

    photo = io.BytesIO()
    Image.new("RGB", (1500, 2000), "white").save(photo, format="JPEG")
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        message = {"role": "assistant", "content": '{"text": "ok"}'}
        return httpx.Response(200, json={"message": message, "done": True, "done_reason": "stop"})

    await ollama(handler).structured(
        prompt=PROMPT, input="Page 1", schema=Page, images=(PageImage(photo.getvalue(), "image/jpeg"),)
    )
    (image,) = sent[0]["messages"][1]["images"]
    with Image.open(io.BytesIO(base64.b64decode(image))) as received:
        assert max(received.size) == MAX_IMAGE_SIDE and received.size[0] < received.size[1]
    small = io.BytesIO()
    Image.new("RGB", (800, 600)).save(small, format="PNG")
    assert shrink(small.getvalue(), MAX_IMAGE_SIDE) == small.getvalue()  # déjà petite : intacte
    assert shrink(b"pas une image", MAX_IMAGE_SIDE) == b"pas une image"


CRASH = (
    '{"error":"error reading llama-server response: read tcp 127.0.0.1:55879->127.0.0.1:53792: '
    "wsarecv: Une connexion existante a dû être fermée par l'hôte distant.\"}"
)


async def test_crash_while_reading_a_photo_retries_with_a_smaller_photo() -> None:
    """Rapport du 25/09 (RX 6600, qwen2.5vl:7b) : Ollama s'arrête au milieu de la lecture."""
    import base64
    import io

    from PIL import Image

    from app.ai.providers.ollama import MAX_IMAGE_SIDE, RETRY_IMAGE_SIDE

    photo = io.BytesIO()
    Image.new("RGB", (1500, 2000), "white").save(photo, format="JPEG")
    sides: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        (image,) = json.loads(request.content)["messages"][1]["images"]
        with Image.open(io.BytesIO(base64.b64decode(image))) as received:
            sides.append(max(received.size))
        if len(sides) == 1:
            return httpx.Response(500, text=CRASH)
        message = {"role": "assistant", "content": '{"text": "ok"}'}
        return httpx.Response(200, json={"message": message, "done": True, "done_reason": "stop"})

    result = await ollama(handler).structured(
        prompt=PROMPT, input="Page 1", schema=Page, images=(PageImage(photo.getvalue(), "image/jpeg"),)
    )
    assert result.output.text == "ok" and sides == [MAX_IMAGE_SIDE, RETRY_IMAGE_SIDE]


async def test_crash_twice_explains_the_graphics_memory() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(500, text=CRASH)

    image = (PageImage(b"\xff\xd8jpeg", "image/jpeg"),)
    with pytest.raises(AIError, match="s'est arrêté pendant le calcul") as caught:
        await ollama(handler).structured(prompt=PROMPT, input="x", schema=Page, images=image)
    assert len(calls) == 2 and "llama-server" in str(caught.value)
    # Sans photo aussi, un nouvel essai : le moteur redémarre.
    with pytest.raises(AIError, match="s'est arrêté"):
        await ollama(handler).structured(prompt=PROMPT, input="x", schema=Page)
    assert len(calls) == 4

    from app.services.lesson_diagnostics import explain

    assert "LUDIFUN_OLLAMA_NUM_CTX" in explain(str(caught.value))


async def test_engine_restarting_is_retried() -> None:
    """Rapport du 25/09, 15 h 02 : « health resp … connectex » juste après un arrêt du moteur."""
    restarting = (
        '{"error":"health resp: Get \\"http://127.0.0.1:55585/health\\": dial tcp 127.0.0.1:55585: '
        "connectex: Aucune connexion n'a pu être établie\"}"
    )
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(500, text=restarting)
        message = {"role": "assistant", "content": '{"text": "ok"}'}
        return httpx.Response(200, json={"message": message, "done": True, "done_reason": "stop"})

    result = await ollama(handler).structured(prompt=PROMPT, input="x", schema=Page)
    assert result.output.text == "ok" and len(calls) == 2


async def test_one_request_at_a_time_per_ollama_server() -> None:
    """Deux leçons envoyées coup sur coup : Ollama reçoit les lectures l'une après l'autre."""
    running = 0
    most = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal running, most
        running += 1
        most = max(most, running)
        await asyncio.sleep(0.05)
        running -= 1
        message = {"role": "assistant", "content": '{"text": "ok"}'}
        return httpx.Response(200, json={"message": message, "done": True, "done_reason": "stop"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    first = OllamaProvider("http://pc:11434", MODELS, client=client)
    second = OllamaProvider("http://pc:11434/", MODELS, client=client)  # même serveur
    await asyncio.gather(
        *(llm.structured(prompt=PROMPT, input="x", schema=Page) for llm in (first, second, first))
    )
    assert most == 1


async def test_photos_are_read_as_plain_text_one_page_at_a_time() -> None:
    """Lecture des photos avec Ollama : texte libre (pas de JSON imposé, qui fait tourner qwen en
    boucle), une page à la fois ; la qualité de chaque page se déduit du texte."""
    from app.ai.ocr.vision_llm import VisionLLMOcr

    answers = ["La Révolution française\nEn 1789…", "Les [illisible] de 1789", "[illisible]"]
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append(body)
        text = answers[len(sent) - 1]
        return httpx.Response(
            200,
            json={
                "message": {"content": text},
                "done_reason": "stop",
                "prompt_eval_count": 900,
                "eval_count": 40,
            },
        )

    photo = PageImage(b"\xff\xd8jpeg", "image/jpeg")
    result = await VisionLLMOcr(ollama(handler)).extract((photo, photo, photo))
    assert len(sent) == 3 and all("format" not in body for body in sent)
    assert all(len(body["messages"][1]["images"]) == 1 for body in sent)
    assert "sans JSON" in sent[0]["messages"][0]["content"]
    assert [p.quality for p in result.output.pages] == ["good", "partial", "unreadable"]
    assert result.output.text.startswith("La Révolution française")
    assert (result.usage.input_tokens, result.usage.output_tokens) == (2700, 120)


async def test_each_call_logs_where_the_time_went(caplog: pytest.LogCaptureFixture) -> None:
    """Pour `Surveiller-Ludifun.bat` : une ligne technique par appel, sans texte de leçon."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {"content": '{"text": "Le secret de la leçon"}'},
                "done_reason": "stop",
                "load_duration": 71_000_000_000,
                "prompt_eval_count": 1300,
                "prompt_eval_duration": 4_000_000_000,
                "eval_count": 520,
                "eval_duration": 20_000_000_000,
            },
        )

    caplog.set_level("INFO", logger="ludifun.ai")
    await ollama(handler).structured(
        prompt=Prompt("analysis", "v9", "x"), input="Le secret de la leçon", schema=Page
    )
    (line,) = [r.getMessage() for r in caplog.records if r.name == "ludifun.ai"]
    assert line.startswith("Ollama : analysis : ")
    assert "chargement 71 s" in line and "lecture 1300 jetons en 4 s" in line
    assert "écriture 520/3500 jetons à 26 jetons/s" in line and line.endswith("fin : stop")
    assert "secret" not in line
