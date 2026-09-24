"""Limites et verrous ajoutés lors de l'audit : mémoire du limiteur, débit par appareil,
tailles maximales, plafond IA journalier, courses sur les jetons, export des données."""

import asyncio
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.api import deps
from app.api.body_limit import BodySizeLimit
from app.db.models import AiRun
from app.security.rate_limit import RateLimiter
from app.services.email import MemoryEmailSender
from tests.api.helpers import PHOTO, auth, family_with_device, register, upload_lesson


def test_rate_limiter_forgets_expired_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    limiter = RateLimiter()
    for i in range(50):
        limiter.hit(f"login:ip:{i}@example.fr", 5, 60)
    assert limiter.exceeded("jamais-vu", 5, 60) is None and len(limiter) == 50  # pas de clé créée
    clock[0] += 61
    assert limiter.exceeded("login:ip:0@example.fr", 5, 60) is None
    assert len(limiter) == 49  # une clé expirée est libérée dès qu'on la consulte
    limiter.purge(60)
    assert len(limiter) == 0  # les autres au nettoyage
    for _ in range(5):
        limiter.hit("k", 5, 60)
    assert limiter.hit("k", 5, 60) is not None  # la limite elle-même est inchangée


async def test_device_request_limit(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deps, "DEVICE_REQUESTS", (3, 60.0))
    token = (await family_with_device(client))["device"]
    statuses = [(await client.get("/v1/me", headers=auth(token))).status_code for _ in range(4)]
    assert statuses == [200, 200, 200, 429]


async def test_attempt_response_size_is_bounded(client: AsyncClient) -> None:
    token = (await family_with_device(client))["device"]
    lesson = await upload_lesson(client, token)
    session = (await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))).json()
    r = await client.post(
        f"/v1/sessions/{session['id']}/attempts",
        json={"item_id": session["items"][0]["id"], "response": {"text": "x" * 20_000}},
        headers=auth(token),
    )
    assert r.status_code == 422


async def _echo(request: Request) -> JSONResponse:
    return JSONResponse({"bytes": len(await request.body())})


@pytest.mark.parametrize("chunked", [False, True])
async def test_body_size_limit(chunked: bool) -> None:
    app = BodySizeLimit(Starlette(routes=[Route("/", _echo, methods=["POST"])]), max_bytes=1000)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        assert (await client.post("/", content=b"x" * 1000)).json() == {"bytes": 1000}

        async def stream(size: int) -> AsyncIterator[bytes]:  # sans Content-Length
            for _ in range(size // 100):
                yield b"x" * 100

        big = stream(5000) if chunked else b"x" * 5000
        r = await client.post("/", content=big)
        assert r.status_code == 413 and r.json()["error"]["code"] == "request_too_large"


async def test_lesson_upload_is_bounded(app: FastAPI, client: AsyncClient) -> None:
    token = (await family_with_device(client))["device"]
    too_big = PHOTO + b"0" * (6 * 8 * 2**20 + 2**20)  # au-delà de 6 photos de 8 Mo
    r = await client.post(
        "/v1/lessons", files=[("pages", ("p.jpg", too_big, "image/jpeg"))], headers=auth(token)
    )
    assert r.status_code == 413


async def test_daily_ai_budget(app: FastAPI, client: AsyncClient, db: AsyncSession) -> None:
    app.state.settings = app.state.settings.model_copy(update={"ai_daily_budget_usd": 1.0})
    token = (await family_with_device(client))["device"]
    await upload_lesson(client, token)  # IA factice : 0 $
    db.add(
        AiRun(
            stage="analysis",
            provider="claude",
            model="claude-opus-5",
            prompt_version="v1",
            input_tokens=100_000,  # 0,50 $
            output_tokens=40_000,  # 1,00 $
            latency_ms=1000,
            status="ok",
            created_at=datetime.now(UTC),
        )
    )
    await db.commit()
    files = [("pages", ("p.jpg", PHOTO, "image/jpeg"))]
    r = await client.post("/v1/lessons", files=files, headers=auth(token))
    assert r.status_code == 503 and r.json()["error"]["code"] == "ai_budget_exhausted"
    assert 0 < int(r.headers["Retry-After"]) <= 86_401
    app.state.settings = app.state.settings.model_copy(update={"ai_daily_budget_usd": None})
    assert (await client.post("/v1/lessons", files=files, headers=auth(token))).status_code == 202


async def test_simultaneous_registrations(client: AsyncClient) -> None:
    body = {"email": "meme@example.fr", "password": "un mot de passe solide", "accepted_privacy_policy": True}
    responses = await asyncio.gather(*(client.post("/v1/auth/register", json=body) for _ in range(3)))
    assert sorted(r.status_code for r in responses) == [201, 409, 409]


async def test_reset_invalidates_other_reset_links(client: AsyncClient, mailer: MemoryEmailSender) -> None:
    await register(client)
    mailer.sent.clear()  # « Confirmez votre adresse »
    for _ in range(2):
        await client.post("/v1/auth/password-reset", json={"email": "parent@example.fr"})
    first, second = (m.body.split("jeton=")[1].split()[0] for m in mailer.sent)
    confirm = "/v1/auth/password-reset/confirm"
    assert (
        await client.post(confirm, json={"token": second, "new_password": "un nouveau mot de passe"})
    ).status_code == 204
    assert (
        await client.post(confirm, json={"token": first, "new_password": "encore un autre mot de passe"})
    ).status_code == 400


async def test_child_data_export(client: AsyncClient) -> None:
    family = await family_with_device(client)
    lesson = await upload_lesson(client, family["device"])
    session = (
        await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(family["device"]))
    ).json()
    await client.post(
        f"/v1/sessions/{session['id']}/attempts",
        json={"item_id": session["items"][0]["id"], "response": {"skipped": True}},
        headers=auth(family["device"]),
    )
    url = f"/v1/children/{family['child']['id']}/export"
    r = await client.get(url, headers=auth(family["parent"]))
    assert r.status_code == 200
    assert r.headers["content-disposition"].startswith('attachment; filename="ludifun-')
    data = r.json()
    assert data["format"] == "ludifun-export-v1"
    assert data["child"]["display_name"] == "Emma" and data["child"]["parental_consent_at"]
    assert len(data["devices"]) == 1
    exported = data["lessons"][0]
    assert exported["title"] == lesson["title"] and exported["text"] and exported["notions"]
    assert data["sessions"][0]["answers"][0]["response"] == {"skipped": True}

    # Séparation : pas pour l'appareil de l'enfant, pas pour un autre parent.
    assert (await client.get(url, headers=auth(family["device"]))).status_code == 403
    stranger = (await register(client, "autre@example.fr"))["access_token"]
    assert (await client.get(url, headers=auth(stranger))).status_code == 404
