"""L'espace parent choisit l'IA de la famille (Ollama conseillé) ; les leçons des enfants de la
famille passent ensuite par elle. La clé est chiffrée et jamais renvoyée."""

from typing import Any

import httpx
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import AiChoice
from app.ai.ocr.vision_llm import VisionLLMOcr
from app.ai.ports import LLMProvider, OcrProvider
from app.ai.providers.fake import FakeProvider
from app.config import Settings
from app.db.models import AiRun, FamilyAiSettings
from app.services.ai_settings import decrypt
from tests.api.helpers import auth, family_with_device, upload_lesson


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

    row = await db.scalar(select(FamilyAiSettings))
    assert row is not None and row.api_key_encrypted is not None
    assert b"sk-ant" not in row.api_key_encrypted
    assert decrypt(app.state.settings, row.api_key_encrypted) == "sk-ant-secret-1234"

    # Même fournisseur, sans clé : la clé enregistrée est gardée ; autre fournisseur : il en faut une.
    kept = await put(client, parent, {"provider": "claude", "model": "claude-sonnet-5"})
    assert kept["family"]["key_hint"] == "…1234" and kept["family"]["model"] == "claude-sonnet-5"
    await put(client, parent, {"provider": "mistral"}, 422)
    switched = await put(client, parent, {"provider": "mistral", "api_key": "mistral-key-9876"})
    assert switched["family"]["key_hint"] == "…9876"


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


async def test_connection_test(app: FastAPI, client: AsyncClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://localhost:11434/api/tags"
        return httpx.Response(200, json={"models": [{"name": "qwen2.5vl:7b"}]})

    app.state.ai_check_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    parent = (await family_with_device(client))["parent"]
    r = await client.post("/v1/parent/ai/test", json={"provider": "ollama"}, headers=auth(parent))
    assert r.status_code == 200, r.text
    assert r.json() == {
        "ok": True,
        "message": "Ollama répond, « qwen2.5vl:7b » est installé.",
        "models": ["qwen2.5vl:7b"],
    }
