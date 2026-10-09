"""Leçon de maths : des exercices calculés par le code s'ajoutent à ceux de la leçon, à la classe
de l'enfant, sans être enregistrés (recalculés à chaque chargement)."""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.fake import FakeProvider
from app.db import models
from app.services.lesson_store import load_units
from tests.api.helpers import auth
from tests.api.test_skills import fractions_lesson


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
