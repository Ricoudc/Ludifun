import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.base import Base
from app.db.models import (
    AiRun,
    Attempt,
    AttemptEvidence,
    Child,
    Device,
    Family,
    FamilyMember,
    KnowledgeItem,
    KnowledgeMastery,
    KnowledgeMaterial,
    Lesson,
    LessonPage,
    Parent,
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
    parent = Parent(email=f"{uuid.uuid4()}@example.fr", password_hash="x", privacy_accepted_at=now)
    family = Family()
    db.add_all([parent, family])
    await db.flush()
    child = Child(family_id=family.id, display_name="Emma", grade="CM1", parental_consent_at=now)
    db.add_all([FamilyMember(family_id=family.id, parent_id=parent.id, role="owner"), child])
    await db.flush()
    db.add(Device(child_id=child.id, token_hash=uuid.uuid4().bytes))
    lesson = Lesson(child_id=child.id, status="ready", page_count=1, subject="history", grade="CM1")
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
        child_id=child.id,
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
                child_id=child.id,
                knowledge_id=knowledge.id,
                score=100,
                box=2,
                next_review_at=now,
                last_practiced_at=now,
            ),
        ]
    )
    await db.commit()
    return {"family": family.id, "parent": parent.id, "lesson": lesson.id, "knowledge": knowledge.id}


async def test_deleting_a_family_erases_all_its_data(db: AsyncSession) -> None:
    """Droit à l'effacement (§16.2) : la suppression du compte parent repose sur ces cascades."""
    ids = await create_full_lesson(db)
    await db.delete(await db.get(Family, ids["family"]))
    await db.delete(await db.get(Parent, ids["parent"]))
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
    child_id = (await db.execute(select(Child.id))).scalar_one()
    for bad in ({"status": "done"}, {"page_count": 7}, {"failure_reason": "oops", "status": "failed"}):
        db.add(Lesson(**{"child_id": child_id, "status": "uploaded", "page_count": 1, **bad}))
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()
    assert ids


async def test_migration_0003_fills_levels_from_existing_data(engine: AsyncEngine, db: AsyncSession) -> None:
    """Les séances déjà jouées donnent les niveaux validés ; le matériel, les niveaux exigés."""
    ids = await create_full_lesson(db)  # k1 (date) : un QCM réussi
    lesson, k1 = ids["lesson"], ids["knowledge"]
    session = await db.scalar(select(RevisionSession).where(RevisionSession.lesson_id == lesson))
    assert session is not None
    session.status = "completed"
    material = await db.get(KnowledgeMaterial, k1)
    assert material is not None
    material.material = {"cloze": {"text": "En ___", "answers": ["1789"]}, "questions": []}
    k2 = KnowledgeItem(
        lesson_id=lesson, key="k2", type="rule", label="Règle", importance=4, position=1,
        statement="On compare les numérateurs.", source_excerpt="compare",
    )  # fmt: skip
    db.add(k2)
    await db.flush()
    child_id = await db.scalar(select(KnowledgeMastery.child_id))
    db.add_all(
        [
            KnowledgeMaterial(
                knowledge_id=k2.id,
                material={"questions": [{"difficulty": 3}], "flashcard": {"front": "a", "back": "b"}},
                prompt_version="v1",
            ),
            KnowledgeMastery(
                child_id=child_id,
                knowledge_id=k2.id,
                score=100,
                box=2,
                next_review_at=datetime.now(UTC),
                last_practiced_at=datetime.now(UTC),
            ),
        ]
    )
    answers = [("FILL_BLANK", 2, k1, "0"), ("MCQ", 3, k2.id, "1")]  # texte à trous raté, application réussie
    for position, (activity, difficulty, knowledge, result) in enumerate(answers, start=2):
        item = SessionItem(
            session_id=session.id, position=position, block="core", activity_type=activity,
            difficulty=difficulty, knowledge_ids=[knowledge], payload={}, solution={},
        )  # fmt: skip
        db.add(item)
        await db.flush()
        attempt = Attempt(session_item_id=item.id, response={}, score=Decimal(result))
        db.add(attempt)
        await db.flush()
        db.add(
            AttemptEvidence(
                attempt_id=attempt.id, knowledge_id=knowledge, result=Decimal(result), weight=Decimal("1")
            )
        )
    await db.commit()

    await run_alembic("downgrade", "0002")
    await run_alembic("upgrade", "head")

    async with engine.connect() as conn:
        rows = (await conn.execute(select(KnowledgeItem.key, KnowledgeItem.required_levels))).all()
        required = {key: value for key, value in rows}
        mastery_rows = (
            await conn.execute(select(KnowledgeMastery.knowledge_id, KnowledgeMastery.levels))
        ).all()
        levels = {key: value for key, value in mastery_rows}
        items = (
            await conn.execute(
                select(SessionItem.activity_type, SessionItem.difficulty, SessionItem.cognitive_level)
            )
        ).all()
    assert required == {"k1": [1, 2], "k2": [1, 2, 3]}
    assert levels == {k1: [1], k2.id: [3]}
    assert sorted(items) == [("FILL_BLANK", 2, 2), ("MCQ", 1, 1), ("MCQ", 3, 3)]


async def test_migration_0013_keeps_the_family_ai_setting(engine: AsyncEngine, db: AsyncSession) -> None:
    """Le réglage d'IA d'avant (un seul, clé comprise) devient l'IA active et son réglage."""
    await db.commit()
    await run_alembic("downgrade", "0012")
    async with engine.begin() as conn:
        family_id = uuid.uuid4()
        await conn.execute(
            text("INSERT INTO families (id, created_at) VALUES (:id, now())"), {"id": family_id}
        )
        await conn.execute(
            text(
                "INSERT INTO family_ai_settings "
                "(family_id, provider, model, base_url, api_key_encrypted, key_hint, updated_at) "
                "VALUES (:id, 'claude', 'claude-sonnet-5', NULL, :key, '…1234', now())"
            ),
            {"id": family_id, "key": b"chiffree"},
        )
    await run_alembic("upgrade", "head")
    async with engine.connect() as conn:
        active = (await conn.execute(text("SELECT provider FROM family_ai_settings"))).all()
        saved = (
            await conn.execute(
                text("SELECT provider, model, api_key_encrypted, key_hint FROM family_ai_providers")
            )
        ).all()
    assert [tuple(row) for row in active] == [("claude",)]
    assert [tuple(row) for row in saved] == [("claude", "claude-sonnet-5", b"chiffree", "…1234")]
