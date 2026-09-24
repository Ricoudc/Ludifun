"""Critère de fin de l'étape 7 : le parcours complet de l'enfant, par l'API.

Photo → leçon → séance → réponses (Emma ne connaît pas les États généraux) →
reprise des erreurs → bilan → maîtrise enregistrée → « Revoir mes erreurs » →
mission du jour, les jours suivants.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.db.models import KnowledgeItem, KnowledgeMastery, SessionItem
from app.domain.simulated_pupil import Knows, respond
from app.services.learning import activity_of
from tests.api.helpers import auth, family_with_device, upload_lesson

SOLUTION_KEYS = {"choice_id", "value", "answers", "pairs", "knowledge_by_left", "knowledge_by_statement"}


async def knowledge_keys(db: AsyncSession) -> dict[uuid.UUID, str]:
    return {row.id: row.key for row in await db.scalars(select(KnowledgeItem))}


async def play(
    client: AsyncClient,
    db: AsyncSession,
    token: str,
    session_id: str,
    items: list[dict[str, Any]],
    knows: Knows,
) -> list[dict[str, Any]]:
    """Répond à chaque activité comme un élève qui connaît certaines notions, y compris aux
    activités de remédiation insérées en cours de route (étape 17)."""
    keys = await knowledge_keys(db)
    feedback = []
    queue = list(items)
    while queue:
        item = queue.pop(0)
        row = await db.get(SessionItem, uuid.UUID(item["id"]))
        assert row is not None
        response = respond(activity_of(row, keys), knows)
        r = await client.post(
            f"/v1/sessions/{session_id}/attempts",
            json={"item_id": item["id"], "response": response, "duration_ms": 8000},
            headers=auth(token),
        )
        assert r.status_code == 200, r.text
        feedback.append(r.json())
        queue = r.json()["inserted_items"] + queue
        keys = await knowledge_keys(db)
    return feedback


@pytest.fixture
def now(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    """Horloge de l'API, avançable dans le test : now[0] += timedelta(days=2)."""
    current = [datetime.now(UTC)]
    monkeypatch.setattr(clock, "now", lambda: current[0])
    return current


async def test_full_child_journey(client: AsyncClient, db: AsyncSession, now: list[datetime]) -> None:
    token = (await family_with_device(client))["device"]
    lesson = await upload_lesson(client, token, pages=2)
    by_label = {k["label"]: k["id"] for k in lesson["knowledge"]}
    etats_generaux = by_label["États généraux"]
    knows: Knows = lambda key: key != "k3"  # noqa: E731

    # Mission du jour : la leçon qui vient d'être ajoutée.
    mission = (await client.get("/v1/me/mission", headers=auth(token))).json()
    assert (mission["lesson"]["id"], mission["reason"]) == (lesson["id"], "latest")
    assert mission["estimated_minutes"] >= 3

    # Écran 4 : la séance.
    session = (await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))).json()
    assert session["kind"] == "first" and session["status"] == "active" and not session["express"]
    assert [i["block"] for i in session["items"]] == ["warmup"] * 3 + ["core"] * 3 + ["match", "speed"]
    assert all(not SOLUTION_KEYS & set(i["payload"]) for i in session["items"])  # jamais la solution
    reopened = (
        await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))
    ).json()
    assert reopened["id"] == session["id"]  # rouvrir l'écran reprend la séance en cours

    # Écrans 5 et 6 : réponses et corrections.
    replay_too_early = await client.post(f"/v1/sessions/{session['id']}/replay", headers=auth(token))
    assert replay_too_early.status_code == 409
    feedback = await play(client, db, token, session["id"], session["items"], knows)
    assert any(f["result"] == "correct" for f in feedback) and any(f["result"] != "correct" for f in feedback)
    wrong = next(f for f in feedback if f["result"] == "incorrect")
    assert wrong["correct_answer"]
    again = await client.post(
        f"/v1/sessions/{session['id']}/attempts",
        json={"item_id": session["items"][0]["id"], "response": {"choice_id": "a"}},
        headers=auth(token),
    )
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_answered"
    resumed = (await client.get(f"/v1/sessions/{session['id']}", headers=auth(token))).json()
    assert all(i["attempt"] is not None for i in resumed["items"])

    # Reprise des erreurs : uniquement les États généraux ; idempotente.
    replay = (await client.post(f"/v1/sessions/{session['id']}/replay", headers=auth(token))).json()["items"]
    assert replay and all(i["block"] == "replay" and i["knowledge_ids"] == [etats_generaux] for i in replay)
    same = (await client.post(f"/v1/sessions/{session['id']}/replay", headers=auth(token))).json()["items"]
    assert [i["id"] for i in same] == [i["id"] for i in replay]
    await play(client, db, token, session["id"], replay, lambda _: True)

    # Écran 7 : bilan.
    report = (await client.post(f"/v1/sessions/{session['id']}/complete", headers=auth(token))).json()
    statuses = {k["id"]: k["status"] for k in report["knowledge"]}
    assert statuses.pop(etats_generaux) in ("to_review", "not_mastered")
    assert set(statuses.values()) == {"mastered"}
    assert report["knowledge"][0]["id"] == etats_generaux  # la plus fragile en tête
    assert 5 <= report["score_on_10"] < 10
    assert sum(report["counts"].values()) == len(report["knowledge"])
    assert report["can_review_errors"] and not report["lesson_mastered"]
    assert datetime.fromisoformat(report["next_review_at"]) == now[0] + timedelta(days=1)
    assert await db.scalar(select(func.count()).select_from(KnowledgeMastery)) == len(report["knowledge"])
    closed = await client.post(f"/v1/sessions/{session['id']}/complete", headers=auth(token))
    assert closed.status_code == 409

    # « Revoir mes erreurs ».
    errors = await client.post(f"/v1/sessions/{session['id']}/errors-session", headers=auth(token))
    assert errors.status_code == 201
    assert {k for i in errors.json()["items"] for k in i["knowledge_ids"]} == {etats_generaux}
    assert errors.json()["kind"] == "errors"

    # Le lendemain : la leçon est due, la séance commence par les États généraux.
    now[0] += timedelta(days=1, minutes=1)
    mission = (await client.get("/v1/me/mission", headers=auth(token))).json()
    assert (mission["lesson"]["id"], mission["reason"]) == (lesson["id"], "due")
    listed = (await client.get("/v1/lessons", headers=auth(token))).json()[0]
    assert listed["due"] and not listed["mastered"]
    review = (await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))).json()
    assert review["kind"] == "review"
    assert review["items"][0]["knowledge_ids"] == [etats_generaux]


async def test_nothing_to_review_when_everything_is_mastered(
    client: AsyncClient, db: AsyncSession, now: list[datetime]
) -> None:
    token = (await family_with_device(client))["device"]
    lesson = await upload_lesson(client, token)
    session = (await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))).json()
    await play(client, db, token, session["id"], session["items"], lambda _: True)
    await client.post(f"/v1/sessions/{session['id']}/complete", headers=auth(token))
    # Tout est su à tous les niveaux et rien n'est dû avant longtemps (y compris les notions pas
    # encore travaillées).
    await db.execute(
        update(KnowledgeMastery).values(
            score=100, box=5, next_review_at=now[0] + timedelta(days=14), levels=[1, 2, 3]
        )
    )
    for item in await db.scalars(select(KnowledgeItem)):
        if not await db.scalar(
            select(KnowledgeMastery.child_id).where(KnowledgeMastery.knowledge_id == item.id)
        ):
            child_id = await db.scalar(select(KnowledgeMastery.child_id).limit(1))
            db.add(
                KnowledgeMastery(
                    child_id=child_id, knowledge_id=item.id, score=100, box=5, levels=[1, 2, 3],
                    next_review_at=now[0] + timedelta(days=14), last_practiced_at=now[0],
                )
            )  # fmt: skip
    await db.commit()

    r = await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))
    assert r.status_code == 409 and r.json()["error"]["code"] == "nothing_to_review"
    assert (await client.get("/v1/me/mission", headers=auth(token))).json() == {
        "lesson": None,
        "reason": None,
        "estimated_minutes": None,
        "exam": None,
        "daily_minutes": None,
    }
    assert (await client.get("/v1/lessons", headers=auth(token))).json()[0]["mastered"]


async def test_skipped_and_invalid_answers(client: AsyncClient) -> None:
    token = (await family_with_device(client))["device"]
    lesson = await upload_lesson(client, token)
    session = (await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))).json()
    first, second = session["items"][0], session["items"][1]
    url = f"/v1/sessions/{session['id']}/attempts"

    invalid = await client.post(
        url, json={"item_id": first["id"], "response": {"nimporte": 1}}, headers=auth(token)
    )
    assert invalid.status_code == 422 and invalid.json()["error"]["code"] == "invalid_response"
    unknown = await client.post(url, json={"item_id": str(uuid.uuid4()), "response": {}}, headers=auth(token))
    assert unknown.status_code == 404

    # Une activité que l'application ne sait pas afficher est sautée, sans compter dans la note.
    skipped = await client.post(
        url, json={"item_id": first["id"], "response": {"skipped": True}}, headers=auth(token)
    )
    assert skipped.json()["result"] == "skipped"
    wrong = {"choice_id": "a"} if second["type"] == "MCQ" else {"value": True}
    await client.post(url, json={"item_id": second["id"], "response": wrong}, headers=auth(token))
    report = (await client.post(f"/v1/sessions/{session['id']}/complete", headers=auth(token))).json()
    assert report["score_on_10"] in (0.0, 10.0)  # une seule activité comptée
    late = await client.post(
        url, json={"item_id": session["items"][2]["id"], "response": {}}, headers=auth(token)
    )
    assert late.status_code == 409 and late.json()["error"]["code"] == "session_closed"


async def test_sessions_of_another_child_are_invisible(client: AsyncClient) -> None:
    emma = await family_with_device(client, "a@example.fr")
    leo = await family_with_device(client, "b@example.fr")
    lesson = await upload_lesson(client, emma["device"])
    session = (
        await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(emma["device"]))
    ).json()
    for method, path in (
        ("GET", ""),
        ("POST", "/replay"),
        ("POST", "/complete"),
        ("POST", "/errors-session"),
    ):
        r = await client.request(method, f"/v1/sessions/{session['id']}{path}", headers=auth(leo["device"]))
        assert r.status_code == 404, path
    r = await client.post(
        f"/v1/sessions/{session['id']}/attempts",
        json={"item_id": session["items"][0]["id"], "response": {"choice_id": "a"}},
        headers=auth(leo["device"]),
    )
    assert r.status_code == 404
