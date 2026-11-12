"""Outil de démonstration : une famille avec quatre semaines de révisions, jouées par l'API."""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import SecretStr

from app import clock
from app.ai.providers.fake import FakeProvider
from app.config import Settings
from app.tools import demo_family
from app.tools.demo_family import DEFAULT_EMAIL, DEFAULT_PASSWORD, PLAN, DemoError, create_demo_family
from tests.api.helpers import auth


async def login(client: AsyncClient) -> str:
    r = await client.post("/v1/auth/login", json={"email": DEFAULT_EMAIL, "password": DEFAULT_PASSWORD})
    assert r.status_code == 200, r.text
    token: str = r.json()["access_token"]
    return token


async def test_demo_family(app: FastAPI, client: AsyncClient, fake_llm: FakeProvider) -> None:
    real_clock = clock.now
    family = await create_demo_family(client, app.state.database, fake_llm)
    assert clock.now is real_clock  # l'horloge simulée est rendue
    assert family.sessions == len(PLAN) and len(family.link_code) == 6

    parent = await login(client)
    children = {c["display_name"]: c for c in (await client.get("/v1/children", headers=auth(parent))).json()}
    assert children["Emma"]["devices"] == 1 and children["Hugo"]["devices"] == 0

    history = (
        await client.get(f"/v1/children/{family.emma_id}/history", params={"limit": 50}, headers=auth(parent))
    ).json()
    assert len(history["sessions"]) == len(PLAN)
    assert {s["status"] for s in history["sessions"]} == {"completed"}
    started = [datetime.fromisoformat(s["started_at"]) for s in history["sessions"]]
    assert (started[0] - started[-1]).days >= 21  # quatre semaines de révisions
    assert started[0] <= datetime.now(UTC)
    assert history["sessions"][-1]["score_on_10"] < history["sessions"][0]["score_on_10"]  # progrès

    board = (
        await client.get(
            f"/v1/children/{family.emma_id}/dashboard", params={"weeks": 5}, headers=auth(parent)
        )
    ).json()
    assert sum(w["sessions"] for w in board["weeks"]) == len(PLAN)
    assert {s["subject"] for s in board["subjects"]} == {"history", "math", "science"}
    assert board["to_strengthen"]

    hugo = (await client.get(f"/v1/children/{family.hugo_id}/history", headers=auth(parent))).json()
    assert hugo["sessions"] == []

    # Le code affiché lie un vrai téléphone au profil d'Emma.
    linked = await client.post("/v1/link", json={"code": family.link_code})
    assert linked.status_code == 201 and linked.json()["child"]["display_name"] == "Emma"


async def test_existing_account_needs_replace(
    app: FastAPI, client: AsyncClient, fake_llm: FakeProvider
) -> None:
    await create_demo_family(client, app.state.database, fake_llm)
    with pytest.raises(DemoError, match="--replace"):
        await create_demo_family(client, app.state.database, fake_llm)
    again = await create_demo_family(client, app.state.database, fake_llm, replace=True)
    parent = await login(client)
    children = (await client.get("/v1/children", headers=auth(parent))).json()
    assert {c["id"] for c in children} == {again.emma_id, again.hugo_id}  # l'ancienne famille est effacée


async def test_address_taken_with_another_password(
    app: FastAPI, client: AsyncClient, fake_llm: FakeProvider
) -> None:
    await create_demo_family(client, app.state.database, fake_llm, password="un autre mot de passe")
    with pytest.raises(DemoError, match="autre mot de passe"):
        await create_demo_family(client, app.state.database, fake_llm, replace=True)


def test_refused_in_production(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    prod = Settings(environment="prod", jwt_secret=SecretStr("un-vrai-secret-de-production-assez-long"))
    monkeypatch.setattr(demo_family, "get_settings", lambda: prod)
    assert demo_family.main([]) == 2
    assert "production" in capsys.readouterr().err
