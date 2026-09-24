"""Critère de l'étape 20 : la séance rapporte de l'XP selon l'effort, des badges une seule fois,
une série de jours ; « Tu as réussi une notion qui te posait problème » plutôt qu'une note."""

from datetime import datetime, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import KnowledgeItem, KnowledgeMastery
from app.domain.simulated_pupil import Knows
from tests.api.helpers import auth, family_with_device, register, upload_lesson
from tests.api.test_sessions import now, play  # noqa: F401  (fixture)


async def revise(
    client: AsyncClient, db: AsyncSession, token: str, lesson_id: str, knows: Knows
) -> dict[str, Any]:
    session = (await client.post(f"/v1/lessons/{lesson_id}/sessions", json={}, headers=auth(token))).json()
    await play(client, db, token, session["id"], session["items"], knows)
    replay = (await client.post(f"/v1/sessions/{session['id']}/replay", headers=auth(token))).json()["items"]
    await play(client, db, token, session["id"], replay, lambda _: True)
    r = await client.post(f"/v1/sessions/{session['id']}/complete", headers=auth(token))
    assert r.status_code == 200, r.text
    report: dict[str, Any] = r.json()
    return report


async def test_rewards_follow_effort_progress_and_regularity(
    client: AsyncClient,
    db: AsyncSession,
    now: list[datetime],  # noqa: F811
) -> None:
    family = await family_with_device(client)
    other = (await register(client, "autre@example.fr"))["access_token"]  # jeton daté d'aujourd'hui
    token = family["device"]
    lesson = await upload_lesson(client, token)

    # Jour 1 : les États généraux ne sont pas sus.
    first = (await revise(client, db, token, lesson["id"], lambda key: key != "k3"))["rewards"]
    lines = {line["label"]: line["xp"] for line in first["lines"]}
    assert lines["Séance terminée"] == 10 and lines["Activités faites"] > 0
    assert lines["Erreurs revues"] == 5 and "Régularité" not in lines
    assert first["xp"] == sum(lines.values())
    codes = [b["code"] for b in first["new_badges"]]
    assert codes[0] == "first_session" and "errors_reviewed" in codes
    assert all(b["earned_at"] for b in first["new_badges"])
    progress = first["progress"]
    assert (progress["total_xp"], progress["level"], progress["streak_days"]) == (first["xp"], 1, 1)
    assert progress["done_today"] and len(progress["badges"]) == 13
    assert [b["code"] for b in progress["badges"][: len(codes)]] == codes  # gagnés d'abord

    k3 = await db.scalar(select(KnowledgeItem.id).where(KnowledgeItem.key == "k3"))
    before = await db.scalar(select(KnowledgeMastery.score).where(KnowledgeMastery.knowledge_id == k3))
    assert before is not None and before < 60

    # Jour 2 : tout est su, dont la notion ratée la veille.
    now[0] += timedelta(days=1)
    second = (await revise(client, db, token, lesson["id"], lambda _: True))["rewards"]
    lines = {line["label"]: line["xp"] for line in second["lines"]}
    assert lines["Notions enfin réussies"] == 10 and lines["Régularité"] == 5
    assert second["message"] == "🏆 Tu as réussi une notion qui te posait problème : États généraux !"
    assert "comeback" in [b["code"] for b in second["new_badges"]]
    assert "first_session" not in [b["code"] for b in second["new_badges"]]  # une seule fois
    assert second["progress"]["streak_days"] == 2
    assert second["progress"]["total_xp"] == first["xp"] + second["xp"]

    # Le parent voit la même progression ; une autre famille, non.
    child_id = family["child"]["id"]
    seen = (
        await client.get("/v1/me/progress", params={"child_id": child_id}, headers=auth(family["parent"]))
    ).json()
    assert seen == (await client.get("/v1/me/progress", headers=auth(token))).json()
    assert seen["total_xp"] == second["progress"]["total_xp"]
    r = await client.get("/v1/me/progress", params={"child_id": child_id}, headers=auth(other))
    assert r.status_code == 404

    # Deux jours sans réviser : la série repart, l'XP et les badges restent.
    now[0] += timedelta(days=2)
    later = (await client.get("/v1/me/progress", headers=auth(token))).json()
    assert (later["streak_days"], later["done_today"]) == (0, False)
    assert later["total_xp"] == seen["total_xp"]

    export = (await client.get(f"/v1/children/{child_id}/export", headers=auth(family["parent"]))).json()
    assert {b["code"] for b in export["badges"]} >= {"first_session", "comeback"}
    assert sum(s["xp_earned"] or 0 for s in export["sessions"]) == seen["total_xp"]
