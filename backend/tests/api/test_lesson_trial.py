"""Le parent essaie la leçon avant son enfant (§5.84) : la séance que l'enfant aura, corrigée
comme pour lui, sans rien enregistrer ni compter."""

import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.lesson_trial import _plan
from app.db.models import Attempt, Child, KnowledgeMastery, Lesson, RevisionSession, SessionItem
from app.domain.activities.registry import default_registry
from app.domain.simulated_pupil import Knows, respond
from tests.api.helpers import auth, family_with_device, upload_lesson


def _always(value: bool) -> Knows:
    return lambda _: value


def trial_url(family: dict[str, Any], lesson: dict[str, Any], end: str = "trial") -> str:
    return f"/v1/children/{family['child']['id']}/lessons/{lesson['id']}/{end}"


async def _rows(db: AsyncSession) -> list[int]:
    return [
        await db.scalar(select(func.count()).select_from(table)) or 0
        for table in (RevisionSession, SessionItem, Attempt, KnowledgeMastery)
    ]


async def test_the_parent_plays_the_lesson_before_the_child(client: AsyncClient, db: AsyncSession) -> None:
    family = await family_with_device(client, review_lessons=True)
    parent = auth(family["parent"])
    lesson = await upload_lesson(client, family["device"])
    assert lesson["awaiting_parent"] is True  # pas encore validée : c'est le moment d'essayer
    before = await _rows(db)

    started = await client.post(trial_url(family, lesson), headers=parent)
    assert started.status_code == 200, started.text
    trial = started.json()
    assert len(trial["items"]) >= 3 and trial["notions"]
    assert all("solution" not in item for item in trial["items"])
    assert all(item["instruction"] for item in trial["items"])
    assert {k for item in trial["items"] for k in item["knowledge_ids"]} == set(trial["notions"])

    # Chaque activité est corrigée comme pour l'enfant : une réponse juste, puis une fausse.
    child_row = await db.get(Child, uuid.UUID(family["child"]["id"]))
    lesson_row = await db.get(Lesson, uuid.UUID(lesson["id"]))
    assert child_row is not None and lesson_row is not None
    plan, _ = await _plan(db, child_row, lesson_row, default_registry(), int(trial["seed"]))
    results = set()
    for item, planned in zip(trial["items"], plan.items, strict=True):
        for knows in (True, False):
            body = {
                "seed": trial["seed"],
                "plan": trial["plan"],
                "position": item["position"],
                "response": respond(planned.activity, _always(knows)),
            }
            r = await client.post(trial_url(family, lesson, "trial/check"), json=body, headers=parent)
            assert r.status_code == 200, r.text
            assert r.json()["item_id"] == item["id"]
            assert r.json()["inserted_items"] == [] and r.json()["coach"] is None
            results.add(r.json()["result"])
            if knows:
                assert r.json()["result"] == "correct"
            else:
                assert r.json()["correct_answer"]
    assert "incorrect" in results or "partial" in results

    # Rien n'est enregistré ni compté : pas de séance, pas de réponse, la leçon attend toujours.
    assert await _rows(db) == before
    listed = (await client.get("/v1/lessons", headers=auth(family["device"]))).json()
    assert listed[0]["awaiting_parent"] is True


async def test_a_changed_lesson_asks_to_start_the_trial_again(client: AsyncClient) -> None:
    family = await family_with_device(client)
    parent = auth(family["parent"])
    lesson = await upload_lesson(client, family["device"])
    trial = (await client.post(trial_url(family, lesson), headers=parent)).json()
    body = {"seed": trial["seed"], "plan": "autre", "position": 1, "response": {}}
    r = await client.post(trial_url(family, lesson, "trial/check"), json=body, headers=parent)
    assert r.status_code == 409 and r.json()["error"]["code"] == "trial_outdated"

    body["plan"] = trial["plan"]
    r = await client.post(trial_url(family, lesson, "trial/check"), json=body, headers=parent)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_response"
    r = await client.post(
        trial_url(family, lesson, "trial/check"), json={**body, "position": 99}, headers=parent
    )
    assert r.status_code == 404


async def test_two_trials_are_two_different_sessions(client: AsyncClient) -> None:
    family = await family_with_device(client)
    parent = auth(family["parent"])
    lesson = await upload_lesson(client, family["device"])
    first = (await client.post(trial_url(family, lesson), headers=parent)).json()
    second = (await client.post(trial_url(family, lesson), headers=parent)).json()
    assert first["seed"] != second["seed"]
