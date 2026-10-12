"""Leçon de maths : des exercices calculés par le code s'ajoutent à ceux de la leçon, à la classe
de l'enfant, sans être enregistrés (recalculés à chaque chargement)."""

import copy

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.fake import FakeProvider, LessonScript
from app.db import models
from app.domain.knowledge import Theme
from app.services.lesson_store import load_units
from tests.api.helpers import auth, family_with_device, upload_lesson
from tests.api.test_skills import FRACTIONS, fractions_lesson


async def test_a_math_lesson_gets_computed_exercises(
    client: AsyncClient, db: AsyncSession, fake_llm: FakeProvider
) -> None:
    family, lesson = await fractions_lesson(client, fake_llm)
    row = await db.get(models.Lesson, lesson["id"])
    assert row is not None and row.subject == "math"
    units = await load_units(db, row)
    compare = next(u for u in units.units if u.item.label == "Comparer des fractions de même dénominateur")
    own = [q for q in compare.material.questions if not q.generated]
    created = [q for q in compare.material.questions if q.generated]
    assert len(created) >= 10 and {q.difficulty for q in created} == {1, 2, 3}
    stems = [q.stem for u in units.units for q in u.material.questions]
    assert len(stems) == len(set(stems))  # jamais deux fois la même question dans la leçon
    # Rien n'est enregistré : la base ne garde que les questions de la leçon.
    stored = await db.scalar(
        select(models.KnowledgeMaterial.material)
        .join(models.KnowledgeItem, models.KnowledgeItem.id == models.KnowledgeMaterial.knowledge_id)
        .where(models.KnowledgeItem.lesson_id == row.id, models.KnowledgeItem.key == compare.id)
    )
    assert stored is not None and len(stored["questions"]) == len(own)

    # La séance dure au moins 5 minutes.
    r = await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(family["device"]))
    assert r.status_code in (200, 201), r.text
    assert r.json()["estimated_duration_min"] >= 5


async def test_the_theme_chosen_by_the_ai_is_checked_stored_and_used(
    client: AsyncClient, db: AsyncSession, fake_llm: FakeProvider
) -> None:
    """§5.47 : un thème de la liste est gardé et relu ; un thème d'une autre matière est retiré."""
    script = LessonScript.from_file(FRACTIONS)
    analysis = copy.deepcopy(script.analysis)
    analysis["knowledge"][0]["theme"] = "fractions"
    analysis["knowledge"][1]["theme"] = "conjugaison"  # leçon de maths : retiré
    fake_llm.script = LessonScript(script.ocr_text, analysis, script.material)
    fake_llm.library = [fake_llm.script]
    family = await family_with_device(client)
    lesson = await upload_lesson(client, family["device"])
    rows = (
        await db.execute(
            select(models.KnowledgeItem.key, models.KnowledgeItem.theme).where(
                models.KnowledgeItem.lesson_id == lesson["id"]
            )
        )
    ).all()
    themes = {key: theme for key, theme in rows}
    assert themes["k1"] == "fractions" and themes["k2"] is None
    row = await db.get(models.Lesson, lesson["id"])
    assert row is not None
    units = {u.id: u for u in (await load_units(db, row)).units}
    assert units["k1"].item.theme is Theme.FRACTIONS and units["k2"].item.theme is None
