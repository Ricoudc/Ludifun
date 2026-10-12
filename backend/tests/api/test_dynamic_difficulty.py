"""Difficulté dynamique (§36) : les dernières réponses de l'enfant, notion par notion, sont
relues avant de composer la séance suivante."""

import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Lesson
from app.domain.activities.registry import default_registry
from app.domain.difficulty import WINDOW
from app.services.learning import recent_answers
from app.services.lesson_store import load_units
from tests.api.helpers import auth, family_with_device, upload_lesson
from tests.api.test_sessions import play


async def test_recent_answers_are_read_notion_by_notion(client: AsyncClient, db: AsyncSession) -> None:
    family = await family_with_device(client)
    token = family["device"]
    lesson = await upload_lesson(client, token)
    session = (await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))).json()
    await play(client, db, token, session["id"], session["items"], lambda key: key != "k1")
    row = await db.scalar(select(Lesson).where(Lesson.id == uuid.UUID(lesson["id"])))
    assert row is not None
    units = await load_units(db, row)
    history = await recent_answers(db, uuid.UUID(family["child"]["id"]), units, default_registry())
    assert history and all(len(answers) <= WINDOW for answers in history.values())
    # « 1789 » est ratée, les autres notions réussies.
    assert all(a.result < 0.5 for a in history["k1"])
    others = [a for key, answers in history.items() if key != "k1" for a in answers]
    assert others and all(a.result >= 0.8 and not a.helped for a in others)
    assert all(1 <= a.difficulty <= 3 for answers in history.values() for a in answers)
