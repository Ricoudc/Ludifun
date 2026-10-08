"""L'espace parent choisit l'IA de la famille (Ollama conseillé) ; les leçons des enfants de la
famille passent ensuite par elle. La clé est chiffrée et jamais renvoyée."""

import uuid
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import BaseModel, SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import AiChoice
from app.ai.ocr.vision_llm import VisionLLMOcr
from app.ai.ports import AIError, LLMProvider, LLMResult, OcrProvider, PageImage, Prompt, Stage, Usage
from app.ai.providers.fake import FakeProvider
from app.config import Settings
from app.db.models import AiRun, FamilyAiProvider
from app.services.ai_settings import decrypt
from tests.api.helpers import PHOTO, auth, family_with_device, upload_lesson


class NamedFake(FakeProvider):
    """L'IA factice, sous le nom du fournisseur choisi : on voit quelle IA a servi."""

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name


def record_builds(app: FastAPI) -> list[AiChoice]:
    built: list[AiChoice] = []

    def builder(settings: Settings, choice: AiChoice) -> tuple[OcrProvider, LLMProvider]:
        built.append(choice)
        llm = NamedFake(choice.provider)
        return VisionLLMOcr(llm), llm

    app.state.ai_resolver.builder = builder
    return built


async def put(client: AsyncClient, token: str, body: dict[str, Any], expected: int = 200) -> Any:
    r = await client.put("/v1/parent/ai", json=body, headers=auth(token))
    assert r.status_code == expected, r.text
    return r.json()


async def test_parent_chooses_ollama_for_the_family(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    built = record_builds(app)
    family = await family_with_device(client)
    parent, device = family["parent"], family["device"]

    seen = (await client.get("/v1/parent/ai", headers=auth(parent))).json()
    assert seen["family"] is None and seen["server_provider"] == "fake"
    first = seen["providers"][0]
    assert (first["code"], first["recommended"], first["needs_key"], first["custom_url"]) == (
        "ollama",
        True,
        False,
        True,
    )
    assert first["default_url"] == "http://localhost:11434" and first["default_model"] == "qwen2.5vl:7b"
    assert [p["code"] for p in seen["providers"]][-1] == "fake"

    chosen = await put(client, parent, {"provider": "ollama", "model": "gemma3:12b"})
    assert chosen["family"] == {
        "provider": "ollama",
        "model": "gemma3:12b",
        "base_url": "http://localhost:11434",
        "key_hint": None,
        "key_lost": False,
    }

    # Les leçons de l'enfant passent par l'IA de la famille.
    await upload_lesson(client, device)
    providers = set(await db.scalars(select(AiRun.provider)))
    assert providers == {"ollama"}
    assert built[-1] == AiChoice("ollama", "gemma3:12b", "http://localhost:11434", None)

    # Revenir à l'IA du serveur.
    assert (await client.delete("/v1/parent/ai", headers=auth(parent))).status_code == 204
    assert (await client.get("/v1/parent/ai", headers=auth(parent))).json()["family"] is None


async def test_api_keys_are_encrypted_and_never_returned(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    record_builds(app)
    parent = (await family_with_device(client))["parent"]
    await put(client, parent, {"provider": "claude"}, 422)  # clé obligatoire
    saved = await put(client, parent, {"provider": "claude", "api_key": "sk-ant-secret-1234"})
    assert saved["family"]["key_hint"] == "…1234"
    assert (
        "sk-ant" not in str(saved)
        and "sk-ant" not in (await client.get("/v1/parent/ai", headers=auth(parent))).text
    )

    row = await db.scalar(select(FamilyAiProvider))
    assert row is not None and row.api_key_encrypted is not None
    assert b"sk-ant" not in row.api_key_encrypted
    assert decrypt(app.state.settings, row.api_key_encrypted) == "sk-ant-secret-1234"

    # Même IA, sans clé : la clé enregistrée est gardée ; nouvelle IA : il en faut une.
    kept = await put(client, parent, {"provider": "claude", "model": "claude-sonnet-5"})
    assert kept["family"]["key_hint"] == "…1234" and kept["family"]["model"] == "claude-sonnet-5"
    await put(client, parent, {"provider": "mistral"}, 422)
    switched = await put(client, parent, {"provider": "mistral", "api_key": "mistral-key-9876"})
    assert switched["family"]["key_hint"] == "…9876"


async def test_each_ai_keeps_its_own_key(app: FastAPI, client: AsyncClient, db: AsyncSession) -> None:
    """Chaque IA garde sa clé et son modèle : on passe de l'une à l'autre sans rien ressaisir."""
    built = record_builds(app)
    family = await family_with_device(client)
    parent = family["parent"]
    await put(
        client, parent, {"provider": "claude", "api_key": "sk-ant-secret-1234", "model": "claude-sonnet-5"}
    )
    await put(client, parent, {"provider": "mistral", "api_key": "mistral-key-9876"})
    await put(client, parent, {"provider": "ollama", "model": "gemma3:12b"})

    # Retour à Claude sans clé : la sienne est toujours là, avec son modèle.
    back = await put(client, parent, {"provider": "claude", "model": "claude-sonnet-5"})
    assert back["family"] == {
        "provider": "claude",
        "model": "claude-sonnet-5",
        "base_url": None,
        "key_hint": "…1234",
        "key_lost": False,
    }
    assert [(s["provider"], s["key_hint"]) for s in back["saved"]] == [
        ("ollama", None),
        ("claude", "…1234"),
        ("mistral", "…9876"),
    ]
    await upload_lesson(client, family["device"])
    assert set(await db.scalars(select(AiRun.provider))) == {"claude"}
    assert AiChoice("claude", "claude-sonnet-5", None, "sk-ant-secret-1234") in built

    # Le test d'une IA déjà réglée utilise sa clé enregistrée, même si elle n'est pas active.
    app.state.ai_check_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: (
                httpx.Response(200, json={"data": [{"id": "mistral-medium-latest"}]})
                if request.headers.get("Authorization") == "Bearer mistral-key-9876"
                else httpx.Response(401)
            )
        )
    )
    stub = ProbeStub(fails=False)
    app.state.ai_resolver.builder = lambda settings, choice: (VisionLLMOcr(stub), stub)
    app.state.ai_resolver.forget()
    tested = (
        await client.post("/v1/parent/ai/test", json={"provider": "mistral"}, headers=auth(parent))
    ).json()
    assert tested["ok"], tested

    # Revenir à l'IA du serveur garde les clés ; oublier une IA efface la sienne.
    assert (await client.delete("/v1/parent/ai", headers=auth(parent))).status_code == 204
    seen = (await client.get("/v1/parent/ai", headers=auth(parent))).json()
    assert seen["family"] is None and len(seen["saved"]) == 3
    assert (await client.delete("/v1/parent/ai/providers/mistral", headers=auth(parent))).status_code == 204
    assert (await client.delete("/v1/parent/ai/providers/mistral", headers=auth(parent))).status_code == 404
    await put(client, parent, {"provider": "mistral"}, 422)  # clé oubliée
    # Oublier l'IA active : retour au serveur.
    await put(client, parent, {"provider": "claude"})
    assert (await client.delete("/v1/parent/ai/providers/claude", headers=auth(parent))).status_code == 204
    final = (await client.get("/v1/parent/ai", headers=auth(parent))).json()
    assert final["family"] is None and [s["provider"] for s in final["saved"]] == ["ollama"]
    # L'enfant ne peut rien oublier.
    r = await client.delete("/v1/parent/ai/providers/ollama", headers=auth(family["device"]))
    assert r.status_code == 403


async def test_validation_and_separation(app: FastAPI, client: AsyncClient) -> None:
    record_builds(app)
    family = await family_with_device(client)
    parent = family["parent"]
    await put(client, parent, {"provider": "compatible", "model": "gpt-5"}, 422)  # adresse manquante
    await put(client, parent, {"provider": "compatible", "base_url": "ftp://x", "model": "m"}, 422)
    await put(client, parent, {"provider": "inconnu"}, 422)
    ok = await put(
        client,
        parent,
        {
            "provider": "compatible",
            "base_url": "https://ressource.openai.azure.com/openai/v1",
            "model": "gpt-5",
        },
    )
    assert ok["family"]["base_url"] == "https://ressource.openai.azure.com/openai/v1"
    # L'appareil de l'enfant ne touche pas au réglage.
    assert (await client.get("/v1/parent/ai", headers=auth(family["device"]))).status_code == 403
    assert (
        await client.put("/v1/parent/ai", json={"provider": "fake"}, headers=auth(family["device"]))
    ).status_code == 403


async def test_free_urls_are_refused_in_production(app: FastAPI, client: AsyncClient) -> None:
    app.state.settings = app.state.settings.model_copy(update={"allow_custom_ai_url": False})
    parent = (await family_with_device(client))["parent"]
    providers = (await client.get("/v1/parent/ai", headers=auth(parent))).json()["providers"]
    assert {p["code"]: p["available"] for p in providers}["ollama"] is False
    r = await client.put("/v1/parent/ai", json={"provider": "ollama"}, headers=auth(parent))
    assert r.status_code == 403 and r.json()["error"]["code"] == "ai_provider_not_allowed"
    assert Settings(environment="prod", jwt_secret="x" * 40).custom_ai_url_allowed is False
    assert Settings().custom_ai_url_allowed is True


class ProbeStub:
    """Répond à la demande d'essai, ou échoue comme un modèle en panne."""

    name = "ollama"

    def __init__(self, fails: bool) -> None:
        self.fails = fails

    def model_for(self, stage: Stage) -> str:
        return "qwen2.5vl:7b"

    async def structured[T: BaseModel](
        self, *, prompt: Prompt, input: str, schema: type[T], images: tuple[PageImage, ...] = ()
    ) -> LLMResult[T]:
        if self.fails:
            raise AIError("Ollama 500 : out of memory")
        return LLMResult(schema.model_validate({"ok": True}), Usage("ollama", "ollama/x", 1, 1, 1))


async def test_connection_test_checks_service_model_and_a_real_answer(
    app: FastAPI, client: AsyncClient
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen2.5vl:7b"}]})
        return httpx.Response(200, json={"capabilities": ["completion", "vision"]})

    app.state.ai_check_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    stub = ProbeStub(fails=False)
    app.state.ai_resolver.builder = lambda settings, choice: (VisionLLMOcr(stub), stub)
    parent = (await family_with_device(client))["parent"]

    r = await client.post("/v1/parent/ai/test", json={"provider": "ollama"}, headers=auth(parent))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] and body["models"] == ["qwen2.5vl:7b"]
    assert body["message"].startswith(
        "Ollama répond, « qwen2.5vl:7b » est installé. Demande d'essai réussie en"
    )

    stub.fails = True
    app.state.ai_resolver.forget()
    failed = (
        await client.post("/v1/parent/ai/test", json={"provider": "ollama"}, headers=auth(parent))
    ).json()
    assert (
        not failed["ok"] and "la demande d'essai a échoué : Ollama 500 : out of memory" in failed["message"]
    )


async def test_fallback_on_another_family_ai_when_allowed(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    """§147 : si l'IA active ne répond pas, une autre IA de la famille prend le relais — seulement si
    le parent l'a permis (les photos partent là où il l'a choisi)."""
    down = AIError("Ollama injoignable à http://pc:11434 (ConnectError) : est-il lancé sur le PC ?")

    def builder(settings: Settings, choice: AiChoice) -> tuple[OcrProvider, LLMProvider]:
        llm = NamedFake(choice.provider)
        if choice.provider == "ollama":
            llm.overrides.update({"ocr": down, "analysis": down, "material": down})
        return VisionLLMOcr(llm), llm

    app.state.ai_resolver.builder = builder
    family = await family_with_device(client)
    parent = family["parent"]
    await put(client, parent, {"provider": "gemini", "api_key": "gemini-key-5555"})
    settings = await put(client, parent, {"provider": "ollama"})
    assert settings["fallback"] is False

    # Sans permission : pas de repli, l'analyse échoue et dit pourquoi.
    failed = await upload_lesson(client, family["device"])
    assert failed["status"] == "failed" and "joindre Ollama" in failed["diagnostics"]["explanation"]

    # Avec permission : Gemini lit la leçon, et on voit que c'était un repli.
    assert (await put(client, parent, {"provider": "ollama", "fallback": True}))["fallback"] is True
    lesson = await upload_lesson(client, family["device"])
    assert lesson["status"] == "ready"
    first = lesson["diagnostics"]["steps"][0]
    assert first["status"] == "ok" and first["message"].startswith("repli : ollama : Ollama injoignable")
    runs = (await db.scalars(select(AiRun).where(AiRun.lesson_id == uuid.UUID(lesson["id"])))).all()
    assert {r.provider for r in runs} == {"gemini"}
    assert all(r.warnings and r.warnings[0].startswith("repli") for r in runs)
    # Le réglage reste tant que le parent ne le change pas.
    assert (await put(client, parent, {"provider": "ollama"}))["fallback"] is True


async def test_a_key_lost_with_the_server_secret_is_asked_again(
    app: FastAPI, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ludifun réinstallé dans un autre dossier (nouveau secret, même base) : la clé de la
    famille ne se lit plus. L'analyse n'est pas lancée avec une IA sans clé (erreur brute) :
    l'enfant est prévenu, le parent voit qu'il faut coller la clé de nouveau."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def use_secret(secret: str) -> None:  # secret tiré au hasard dans le .env de chaque dossier
        settings: Settings = app.state.settings.model_copy(update={"secrets_key": SecretStr(secret)})
        app.state.settings = app.state.ai_resolver.settings = settings
        app.state.ai_resolver.forget()

    use_secret("ancien-dossier-" + "a" * 32)
    family = await family_with_device(client)
    await put(client, family["parent"], {"provider": "claude", "api_key": "sk-ant-secret-1234"})
    use_secret("nouveau-dossier-" + "b" * 32)

    shown = (await client.get("/v1/parent/ai", headers=auth(family["parent"]))).json()
    assert shown["family"]["key_lost"] is True and shown["family"]["key_hint"] is None
    files = [("pages", ("page.jpg", PHOTO, "image/jpeg"))]
    r = await client.post("/v1/lessons", files=files, headers=auth(family["device"]))
    assert r.status_code == 503 and r.json()["error"]["code"] == "ai_not_configured", r.text

    # La clé collée de nouveau : tout repart.
    again = await put(client, family["parent"], {"provider": "claude", "api_key": "sk-ant-secret-5678"})
    assert again["family"]["key_lost"] is False and again["family"]["key_hint"] == "…5678"
