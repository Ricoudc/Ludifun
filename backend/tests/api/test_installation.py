"""« Tout va bien ? » dans l'espace parent (§5.89) : l'état de l'installation, sans appel payant."""

import httpx
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FamilyAiProvider
from tests.api.helpers import auth, family_with_device, upload_lesson


def by_code(body: dict[str, object]) -> dict[str, dict[str, str]]:
    checks: list[dict[str, str]] = body["checks"]  # type: ignore[assignment]
    return {c["code"]: c for c in checks}


async def test_the_server_ai_and_no_lesson_yet(app: FastAPI, client: AsyncClient) -> None:
    app.state.ai_check_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"data": []}))
    )
    family = await family_with_device(client)
    r = await client.get("/v1/parent/installation", headers=auth(family["parent"]))
    assert r.status_code == 200, r.text
    checks = by_code(r.json())
    assert r.json()["level"] == "ok"
    assert checks["ai"]["level"] == "ok" and "l'IA du serveur" in checks["ai"]["message"]
    assert checks["lessons"]["message"] == "Aucune leçon envoyée pour l'instant."
    assert checks["budget"]["level"] == "ok"
    assert "gpu" not in checks and "review" not in checks


async def test_ollama_overflowing_the_graphics_card_is_explained(app: FastAPI, client: AsyncClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/ps":
            return httpx.Response(
                200,
                json={"models": [{"name": "qwen3-vl:8b", "size": 6_400_000_000, "size_vram": 5_760_000_000}]},
            )
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"name": "qwen3-vl:8b", "size": 6_200_000_000},
                        {"name": "qwen3.5:4b", "size": 3_300_000_000},
                    ]
                },
            )
        return httpx.Response(200, json={"capabilities": ["completion", "vision"]})

    app.state.ai_check_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    family = await family_with_device(client)
    parent = auth(family["parent"])
    saved = await client.put(
        "/v1/parent/ai", json={"provider": "ollama", "model": "qwen3-vl:8b"}, headers=parent
    )
    assert saved.status_code == 200, saved.text

    body = (await client.get("/v1/parent/installation", headers=parent)).json()
    checks = by_code(body)
    assert body["level"] == "warning"
    assert checks["ai"]["level"] == "ok" and "votre IA (ollama)" in checks["ai"]["message"]
    assert checks["gpu"]["level"] == "warning" and "10 %" in checks["gpu"]["message"]
    assert "qwen3.5:4b (3,3 Go)" in checks["gpu"]["action"]


async def test_an_unreadable_key_and_lessons_to_review_are_said(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    app.state.ai_check_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"data": []}))
    )
    family = await family_with_device(client, review_lessons=True)
    parent = auth(family["parent"])
    await upload_lesson(client, family["device"])  # prête, à relire
    saved = await client.put(
        "/v1/parent/ai", json={"provider": "mistral", "api_key": "mistral-key-9876"}, headers=parent
    )
    assert saved.status_code == 200, saved.text
    # Le secret du serveur a changé : la clé enregistrée n'est plus lisible.
    await db.execute(update(FamilyAiProvider).values(api_key_encrypted=b"illisible"))
    await db.commit()

    body = (await client.get("/v1/parent/installation", headers=parent)).json()
    checks = by_code(body)
    assert body["level"] == "error"
    assert checks["ai"]["level"] == "error" and "plus lisible" in checks["ai"]["message"]
    assert "collez de nouveau la clé" in checks["ai"]["action"]
    assert checks["review"]["level"] == "warning" and "1 leçon(s)" in checks["review"]["message"]
    assert "mistral-key" not in str(body)  # jamais la clé
