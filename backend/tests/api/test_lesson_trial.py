"""Le parent essaie la leçon avant son enfant (§5.84) : la séance que l'enfant aura, corrigée
comme pour lui, sans rien enregistrer ni compter."""

import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.lesson_trial import _plan
from app.db.models import (
    Attempt,
    Child,
    KnowledgeItem,
    KnowledgeMastery,
    KnowledgeMaterial,
    Lesson,
    RevisionSession,
    SessionItem,
)
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


async def test_a_full_trial_goes_through_every_notion(client: AsyncClient) -> None:
    family = await family_with_device(client)
    parent = auth(family["parent"])
    lesson = await upload_lesson(client, family["device"])
    full = (await client.post(trial_url(family, lesson) + "?full=true", headers=parent)).json()
    assert full["full"] is True
    assert len(full["notions"]) == full["total_notions"] >= 3
    # La Révolution de référence a une notion secondaire que les séances ne travaillent pas
    # (assez de notions importantes) : elle est dite au parent.
    assert len(full["never_shown"]) == 1
    short = (await client.post(trial_url(family, lesson), headers=parent)).json()
    assert short["full"] is False and len(short["items"]) <= len(full["items"])
    # Une correction de l'essai complet se fait avec « full » : la même séance est recomposée.
    body = {"seed": full["seed"], "plan": full["plan"], "position": 1, "response": {}, "full": True}
    r = await client.post(trial_url(family, lesson, "trial/check"), json=body, headers=parent)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_response"  # et non 409


async def test_a_question_noted_during_the_trial_is_shown_until_it_is_fixed(
    client: AsyncClient, db: AsyncSession
) -> None:
    family = await family_with_device(client, review_lessons=True)
    parent = auth(family["parent"])
    lesson = await upload_lesson(client, family["device"])
    trial = (await client.post(trial_url(family, lesson), headers=parent)).json()
    item = trial["items"][0]
    body = {"seed": trial["seed"], "plan": trial["plan"], "position": item["position"]}

    noted = await client.post(trial_url(family, lesson, "trial/notes"), json=body, headers=parent)
    assert noted.status_code == 200, noted.text
    note = noted.json()
    assert note["knowledge_id"] == item["knowledge_ids"][0] and note["question"]
    assert note["activity_type"] == item["type"]
    again = (await client.post(trial_url(family, lesson, "trial/notes"), json=body, headers=parent)).json()
    assert again["id"] == note["id"]  # la même question notée deux fois : une seule note

    content = (await client.get(trial_url(family, lesson, "content"), headers=parent)).json()
    shown = [n for notion in content["notions"] for n in notion["trial_notes"]]
    assert [n["id"] for n in shown] == [note["id"]]
    # Rien n'est compté pour l'enfant : ni séance ni maîtrise.
    assert await _rows(db) == [0, 0, 0, 0]

    resolved = await client.post(
        trial_url(family, lesson, f"trial-notes/{note['id']}/resolve"), headers=parent
    )
    assert resolved.status_code == 204
    content = (await client.get(trial_url(family, lesson, "content"), headers=parent)).json()
    assert all(notion["trial_notes"] == [] for notion in content["notions"])
    other = str(uuid.uuid4())
    missing = await client.post(trial_url(family, lesson, f"trial-notes/{other}/resolve"), headers=parent)
    assert missing.status_code == 404


async def test_recheck_removes_what_todays_checks_refuse(client: AsyncClient, db: AsyncSession) -> None:
    family = await family_with_device(client)
    parent = auth(family["parent"])
    lesson = await upload_lesson(client, family["device"])
    before = (await client.post(trial_url(family, lesson, "recheck"), headers=parent)).json()
    assert before["removed"] == []  # une leçon d'aujourd'hui passe déjà les contrôles

    # Une leçon analysée avant les contrôles : une question sans son contexte, une affirmation en
    # anglais ; sur une autre notion, toutes les questions sans contexte.
    rows = list(
        await db.scalars(
            select(KnowledgeMaterial)
            .join(KnowledgeItem, KnowledgeItem.id == KnowledgeMaterial.knowledge_id)
            .where(KnowledgeItem.lesson_id == uuid.UUID(lesson["id"]))
            .order_by(KnowledgeItem.position)
        )
    )
    first, second, *_ = (r for r in rows if len(r.material["questions"]) >= 2)
    kept_stem = first.material["questions"][1]["stem"]
    questions = [dict(q) for q in first.material["questions"]]
    questions[0]["stem"] = "Quel est le pluriel de ce mot ?"
    english = "Which word is the subject of the sentence?"
    statements = [*first.material["true_statements"], english]
    first.material = {**first.material, "questions": questions, "true_statements": statements}
    only = [{**q, "stem": "Complète la phrase suivante."} for q in second.material["questions"]]
    second.material = {**second.material, "questions": only}
    await db.commit()

    r = await client.post(trial_url(family, lesson, "recheck"), headers=parent)
    assert r.status_code == 200, r.text
    removed = r.json()["removed"]
    gone = {(x["knowledge_id"], x["element"]) for x in removed if not x["kept"]}
    assert gone == {
        (str(first.knowledge_id), "questions[0]"),
        (str(first.knowledge_id), f"true_statements[{len(statements) - 1}]"),
    }
    # Les dernières questions d'une notion sont gardées et signalées : à corriger soi-même.
    kept = [x for x in removed if x["kept"]]
    assert kept and all(x["knowledge_id"] == str(second.knowledge_id) for x in kept)
    await db.refresh(first)
    await db.refresh(second)
    assert [q["stem"] for q in first.material["questions"]] == [
        kept_stem,
        *[q["stem"] for q in questions[2:]],
    ]
    assert english not in first.material["true_statements"]
    assert len(second.material["questions"]) == len(only)
