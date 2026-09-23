import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.base import Base
from app.db.models import (
    AiRun,
    Attempt,
    AttemptEvidence,
    Device,
    KnowledgeItem,
    KnowledgeMastery,
    KnowledgeMaterial,
    Learner,
    Lesson,
    LessonPage,
    RevisionSession,
    SessionItem,
)
from tests.conftest import run_alembic


async def test_models_match_migrations(engine: AsyncEngine) -> None:
    """Toute modification de app/db/models.py doit avoir sa migration Alembic."""

    def diff(sync_conn: Connection) -> list[Any]:
        context = MigrationContext.configure(sync_conn, opts={"compare_type": True})
        differences: list[Any] = compare_metadata(context, Base.metadata)
        return differences

    async with engine.connect() as conn:
        assert await conn.run_sync(diff) == []


async def test_migrations_downgrade_and_upgrade(engine: AsyncEngine) -> None:
    await run_alembic("downgrade", "base")
    await run_alembic("upgrade", "head")


async def create_full_lesson(db: AsyncSession) -> dict[str, uuid.UUID]:
    """Une leçon avec toutes les tables remplies, comme après une vraie séance."""
    now = datetime.now(UTC)
    device = Device(token_hash=uuid.uuid4().bytes)
    db.add(device)
    await db.flush()
    learner = Learner(device_id=device.id)
    db.add(learner)
    await db.flush()
    lesson = Lesson(learner_id=learner.id, status="ready", page_count=1, subject="history", grade="CM1")
    db.add(lesson)
    await db.flush()
    knowledge = KnowledgeItem(
        lesson_id=lesson.id,
        key="k1",
        type="date",
        label="1789",
        importance=5,
        position=0,
        statement="La Révolution française commence en 1789.",
        source_excerpt="commence en 1789",
    )
    db.add_all([knowledge, LessonPage(lesson_id=lesson.id, page_index=0, ocr_text="…", quality="good")])
    await db.flush()
    session = RevisionSession(
        learner_id=learner.id,
        lesson_id=lesson.id,
        kind="first",
        status="active",
        objective="Connaître 1789",
        estimated_duration_s=480,
        seed=42,
    )
    db.add_all(
        [
            session,
            KnowledgeMaterial(knowledge_id=knowledge.id, material={"tip": "1789"}, prompt_version="v1"),
            AiRun(
                lesson_id=lesson.id,
                stage="analysis",
                provider="fake",
                model="fake",
                prompt_version="v1",
                latency_ms=10,
                status="ok",
            ),
        ]
    )
    await db.flush()
    item = SessionItem(
        session_id=session.id,
        position=1,
        block="warmup",
        activity_type="MCQ",
        difficulty=1,
        knowledge_ids=[knowledge.id],
        payload={"prompt": "?"},
        solution={"choice_id": "b"},
    )
    db.add(item)
    await db.flush()
    attempt = Attempt(session_item_id=item.id, response={"choice_id": "b"}, score=Decimal("1"))
    db.add(attempt)
    await db.flush()
    db.add_all(
        [
            AttemptEvidence(
                attempt_id=attempt.id, knowledge_id=knowledge.id, result=Decimal("1"), weight=Decimal("0.6")
            ),
            KnowledgeMastery(
                learner_id=learner.id,
                knowledge_id=knowledge.id,
                score=100,
                box=2,
                next_review_at=now,
                last_practiced_at=now,
            ),
        ]
    )
    await db.commit()
    return {"device": device.id, "lesson": lesson.id, "knowledge": knowledge.id}


async def test_deleting_a_device_erases_all_its_data(db: AsyncSession) -> None:
    """Droit à l'effacement (§16.2) : DELETE /v1/me repose sur ces cascades."""
    ids = await create_full_lesson(db)
    await db.delete(await db.get(Device, ids["device"]))
    await db.commit()

    for model in Base.metadata.sorted_tables:
        if model.name == "ai_runs":
            continue
        count = (await db.execute(select(func.count()).select_from(model))).scalar_one()
        assert count == 0, f"{model.name} contient encore {count} ligne(s)"

    # Les statistiques de coût IA sont conservées, sans lien vers la leçon supprimée.
    run = (await db.execute(select(AiRun))).scalar_one()
    assert run.lesson_id is None


@pytest.mark.parametrize(
    "field, value",
    [("importance", 6), ("importance", 0), ("type", None)],
)
async def test_knowledge_item_constraints(db: AsyncSession, field: str, value: object) -> None:
    ids = await create_full_lesson(db)
    data = dict(
        lesson_id=ids["lesson"],
        key="k2",
        type="person",
        label="Louis XVI",
        importance=4,
        position=1,
        statement="Louis XVI est roi.",
        source_excerpt="le roi Louis XVI",
    )
    db.add(KnowledgeItem(**{**data, field: value}))
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


async def test_lesson_status_and_page_count_are_checked(db: AsyncSession) -> None:
    ids = await create_full_lesson(db)
    learner_id = (await db.execute(select(Learner.id))).scalar_one()
    for bad in ({"status": "done"}, {"page_count": 7}, {"failure_reason": "oops", "status": "failed"}):
        db.add(Lesson(**{"learner_id": learner_id, "status": "uploaded", "page_count": 1, **bad}))
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()
    assert ids
