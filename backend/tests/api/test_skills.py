"""Étape 13 dans l'API : compétences de la leçon, niveaux de compréhension et niveau 0 à 5."""

import uuid
from datetime import datetime, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.fake import REFERENCE_LESSONS, FakeProvider, LessonScript
from app.db.models import KnowledgeItem, KnowledgeMastery, SessionItem, Skill
from app.domain.understanding import cognitive_level
from tests.api.helpers import auth, family_with_device, upload_lesson
from tests.api.test_sessions import now, play  # noqa: F401  (fixture)

FRACTIONS = REFERENCE_LESSONS / "math_cm2_fractions.json"


async def fractions_lesson(
    client: AsyncClient, fake_llm: FakeProvider
) -> tuple[dict[str, Any], dict[str, Any]]:
    fake_llm.script = LessonScript.from_file(FRACTIONS)
    family = await family_with_device(client)
    return family, await upload_lesson(client, family["device"])


async def test_lesson_skills_and_levels_through_a_session(
    client: AsyncClient,
    db: AsyncSession,
    fake_llm: FakeProvider,
    now: list[datetime],  # noqa: F811
) -> None:
    family, lesson = await fractions_lesson(client, fake_llm)
    token = family["device"]

    # Écran 4 : ce que l'enfant va savoir faire, et ses notions, toutes au niveau 0.
    ids = {k["label"]: k["id"] for k in lesson["knowledge"]}
    assert [s["label"] for s in lesson["skills"]] == [
        "Dire ce qu'est une fraction et nommer ses termes",
        "Comparer deux fractions de même dénominateur",
        "Reconnaître une fraction égale à 1",
    ]
    compare = lesson["skills"][1]
    assert compare["verb"] == "apply" and compare["importance"] == 5 and compare["level"] == 0
    assert compare["knowledge_ids"] == [
        ids["Numérateur"],
        ids["Dénominateur"],
        ids["Comparer des fractions de même dénominateur"],
    ]
    assert {k["level"] for k in lesson["knowledge"]} == {0}

    # Une règle s'applique ; un terme se rappelle.
    rows = (await db.execute(select(KnowledgeItem.label, KnowledgeItem.required_levels))).all()
    required = {label: levels for label, levels in rows}
    assert required["Comparer des fractions de même dénominateur"] == [1, 2, 3]
    assert required["Numérateur"] == [1, 2]

    # Chaque activité enregistre le niveau de compréhension qu'elle sollicite.
    session = (await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))).json()
    for item in session["items"]:
        row = await db.get(SessionItem, uuid.UUID(item["id"]))
        assert row is not None
        assert row.cognitive_level == cognitive_level(row.activity_type, row.difficulty)

    await play(client, db, token, session["id"], session["items"], lambda _: True)
    report = (await client.post(f"/v1/sessions/{session['id']}/complete", headers=auth(token))).json()
    for notion in report["knowledge"]:
        assert notion["previous_level"] == 0
        assert 1 <= notion["level"] <= 4 and notion["explanation"]
    # Première séance réussie : aucune notion ne peut déjà être « très bien maîtrisée » (J+14).
    assert all(n["level"] < 5 for n in report["knowledge"])

    after = (await client.get(f"/v1/lessons/{lesson['id']}", headers=auth(token))).json()
    levels = {k["id"]: k["level"] for k in after["knowledge"]}
    assert {levels[i] for i in {k["id"] for k in report["knowledge"]}} - {0}
    for skill in after["skills"]:
        assert skill["level"] <= min(levels[k] for k in skill["knowledge_ids"]) + 1


async def test_parent_sees_what_is_missing(
    client: AsyncClient,
    db: AsyncSession,
    fake_llm: FakeProvider,
    now: list[datetime],  # noqa: F811
) -> None:
    family, lesson = await fractions_lesson(client, fake_llm)
    parent, child_id = family["parent"], family["child"]["id"]
    token = family["device"]
    session = (await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))).json()
    await play(client, db, token, session["id"], session["items"], lambda _: True)
    await client.post(f"/v1/sessions/{session['id']}/complete", headers=auth(token))

    # Le numérateur : parfaitement réussi, depuis longtemps… mais seulement en QCM.
    numerator = await db.scalar(select(KnowledgeItem.id).where(KnowledgeItem.label == "Numérateur"))
    await db.execute(
        update(KnowledgeMastery)
        .where(KnowledgeMastery.knowledge_id == numerator)
        .values(score=100, box=5, levels=[1], next_review_at=now[0] + timedelta(days=10))
    )
    await db.commit()

    r = await client.get(f"/v1/children/{child_id}/skills", headers=auth(parent))
    assert r.status_code == 200, r.text
    (progress,) = r.json()["lessons"]
    assert progress["lesson_id"] == lesson["id"] and progress["subject"] == "math"
    assert len(progress["skills"]) == 3
    notions = {n["label"]: n for n in progress["notions"]}
    assert notions["Numérateur"]["level"] == {
        "value": 3,
        "label": "En cours d'acquisition",
        "color": "orange",
    }
    assert "retrouver seul" in notions["Numérateur"]["explanation"]
    assert [n["label"] for n in progress["notions"]][:2] == ["Fraction", "Numérateur"]  # ordre de la leçon
    for skill in progress["skills"]:
        assert skill["level"]["label"] and skill["level"]["color"] in ("grey", "red", "orange", "green")
        # §5.52 : bilan de la compétence pour le parent, écrit par le code.
        report = skill["report"]
        assert report["status"] in ("not_started", "to_work", "in_progress", "acquired")
        assert report["summary"]
        if report["status"] in ("to_work", "in_progress"):
            assert report["weakest"] in notions and report["advice"]
            assert f"« {report['weakest']} »" in report["advice"]

    board = (await client.get(f"/v1/children/{child_id}/dashboard", headers=auth(parent))).json()
    weak = {n["label"]: n for n in board["to_strengthen"]}
    assert weak["Numérateur"]["mastery"] == 100
    assert weak["Numérateur"]["level"] == 3 and weak["Numérateur"]["status"] == "to_review"


async def test_skills_without_notions_are_not_kept(
    client: AsyncClient, db: AsyncSession, fake_llm: FakeProvider
) -> None:
    script = LessonScript.from_file(FRACTIONS)
    analysis = {**script.analysis}
    analysis["skills"] = [
        *analysis["skills"],
        {**analysis["skills"][0], "id": "s9", "knowledge_ids": ["k42"]},
    ]
    fake_llm.script = LessonScript(script.ocr_text, analysis, script.material)
    family = await family_with_device(client)
    lesson = await upload_lesson(client, family["device"])
    assert lesson["status"] == "ready"
    assert len(lesson["skills"]) == 3
    assert await db.scalar(select(Skill.key).where(Skill.key == "s9")) is None


async def test_no_lesson_gives_an_empty_list(client: AsyncClient) -> None:
    family = await family_with_device(client)
    r = await client.get(f"/v1/children/{family['child']['id']}/skills", headers=auth(family["parent"]))
    assert r.json() == {"lessons": []}
