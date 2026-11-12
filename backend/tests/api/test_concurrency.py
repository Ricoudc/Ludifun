"""Doubles envois simultanés (double appui, requête rejouée par le réseau) : une seule
prise en compte, et un refus propre pour l'autre, jamais une erreur 500 (audit de septembre 2026)."""

import asyncio
import copy

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.ports import AIError
from app.ai.providers.fake import FakeProvider, analysis_output
from app.db.models import RevisionSession
from app.services import lesson_processing
from tests.api.helpers import auth, family_with_device, upload_lesson
from tests.api.test_sessions import play


async def test_double_complete(client: AsyncClient, db: AsyncSession) -> None:
    token = (await family_with_device(client))["device"]
    lesson = await upload_lesson(client, token)
    session = (await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))).json()
    await play(client, db, token, session["id"], session["items"], lambda key: True)
    url = f"/v1/sessions/{session['id']}/complete"
    responses = await asyncio.gather(*(client.post(url, headers=auth(token)) for _ in range(3)))
    assert sorted(r.status_code for r in responses) == [200, 409, 409], [r.text for r in responses]


async def test_double_start(client: AsyncClient, db: AsyncSession) -> None:
    token = (await family_with_device(client))["device"]
    lesson = await upload_lesson(client, token)
    url = f"/v1/lessons/{lesson['id']}/sessions"
    responses = await asyncio.gather(*(client.post(url, json={}, headers=auth(token)) for _ in range(3)))
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    assert len({r.json()["id"] for r in responses}) == 1
    count = await db.scalar(select(func.count()).select_from(RevisionSession))
    assert count == 1


async def test_double_replay_and_extend(client: AsyncClient, db: AsyncSession) -> None:
    token = (await family_with_device(client))["device"]
    lesson = await upload_lesson(client, token)
    session = (await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))).json()
    await play(client, db, token, session["id"], session["items"], lambda key: key != "k1")
    url = f"/v1/sessions/{session['id']}/replay"
    responses = await asyncio.gather(*(client.post(url, headers=auth(token)) for _ in range(3)))
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    assert len({tuple(i["id"] for i in r.json()["items"]) for r in responses}) == 1


async def test_double_errors_session(client: AsyncClient, db: AsyncSession) -> None:
    token = (await family_with_device(client))["device"]
    lesson = await upload_lesson(client, token)
    session = (await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))).json()
    await play(client, db, token, session["id"], session["items"], lambda key: key != "k1")
    await client.post(f"/v1/sessions/{session['id']}/complete", headers=auth(token))
    url = f"/v1/sessions/{session['id']}/errors-session"
    responses = await asyncio.gather(*(client.post(url, headers=auth(token)) for _ in range(3)))
    assert all(r.status_code == 201 for r in responses), [r.text for r in responses]
    assert len({r.json()["id"] for r in responses}) == 1


async def test_double_retry_runs_one_analysis(client: AsyncClient, fake_llm: FakeProvider) -> None:
    good = analysis_output(copy.deepcopy(fake_llm.script.analysis))
    fake_llm.overrides["analysis"] = lambda attempt, _: AIError("API 529") if attempt == 1 else good
    token = (await family_with_device(client))["device"]
    lesson = await upload_lesson(client, token)
    url = f"/v1/lessons/{lesson['id']}/retry"
    responses = await asyncio.gather(*(client.post(url, headers=auth(token)) for _ in range(3)))
    assert sorted(r.status_code for r in responses) == [202, 409, 409], [r.text for r in responses]
    assert [stage for stage, _ in fake_llm.calls].count("analysis") == 2  # l'échec, puis une relance


async def test_saving_failure_does_not_leave_the_lesson_running(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def broken(*_: object) -> None:
        raise RuntimeError("base indisponible")

    monkeypatch.setattr(lesson_processing, "save_pipeline_result", broken)
    token = (await family_with_device(client))["device"]
    lesson = await upload_lesson(client, token)
    assert (lesson["status"], lesson["failure_reason"]) == ("failed", "ai_error")
