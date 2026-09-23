"""Séances de révision en base : création, réponses, reprise, bilan, erreurs, mission du jour.

La logique pédagogique reste dans le domaine (composeur, activités, notation,
mémorisation) ; ce module la relie à PostgreSQL.
"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as db
from app.domain.activities.base import ActivityCode, BuiltActivity, Grade
from app.domain.activities.registry import ActivityRegistry
from app.domain.composer import Block, NothingToReview, PlannedItem, SessionComposer, SessionPlan
from app.domain.scoring import (
    Evidence,
    KnowledgeStatus,
    SessionOutcome,
    evidence_weight,
    session_rates,
    status,
)
from app.domain.scoring import summarize_session as summarize
from app.services.lesson_store import LessonUnits, load_masteries, load_units, save_masteries

STALE_SESSION = timedelta(hours=24)  # au-delà, une séance non terminée est abandonnée


class LessonNotReady(Exception):
    pass


class SessionClosed(Exception):
    pass


class AlreadyAnswered(Exception):
    pass


class MainNotFinished(Exception):
    pass


def new_seed() -> int:
    return secrets.randbits(62)


def activity_of(item: db.SessionItem, id_to_key: dict[uuid.UUID, str]) -> BuiltActivity:
    return BuiltActivity(
        type=ActivityCode(item.activity_type),
        difficulty=item.difficulty,
        knowledge_ids=[id_to_key[k] for k in item.knowledge_ids],
        payload=item.payload,
        solution=item.solution,
    )


async def session_items(session: AsyncSession, revision: db.RevisionSession) -> list[db.SessionItem]:
    result = await session.scalars(
        select(db.SessionItem)
        .where(db.SessionItem.session_id == revision.id)
        .order_by(db.SessionItem.position)
    )
    return list(result)


async def attempts_by_item(
    session: AsyncSession, revision: db.RevisionSession
) -> dict[uuid.UUID, db.Attempt]:
    result = await session.scalars(
        select(db.Attempt)
        .join(db.SessionItem, db.SessionItem.id == db.Attempt.session_item_id)
        .where(db.SessionItem.session_id == revision.id)
    )
    return {a.session_item_id: a for a in result}


def _persist_plan(
    session: AsyncSession, revision: db.RevisionSession, planned: list[PlannedItem], lesson: LessonUnits
) -> None:
    for item in planned:
        session.add(
            db.SessionItem(
                session_id=revision.id,
                position=item.position,
                block=item.block.value,
                activity_type=item.activity.type.value,
                difficulty=item.activity.difficulty,
                knowledge_ids=[lesson.key_to_id[k] for k in item.activity.knowledge_ids],
                payload=item.activity.payload,
                solution=item.activity.solution,
            )
        )


async def _new_session(
    session: AsyncSession,
    child_id: uuid.UUID,
    lesson: LessonUnits,
    plan: SessionPlan,
    seed: int,
    parent_session_id: uuid.UUID | None = None,
) -> db.RevisionSession:
    revision = db.RevisionSession(
        child_id=child_id,
        lesson_id=lesson.lesson.id,
        kind=plan.kind.value,
        parent_session_id=parent_session_id,
        status="active",
        objective=lesson.lesson.objective or lesson.lesson.title or "Réviser la leçon",
        estimated_duration_s=plan.estimated_duration_s,
        seed=seed,
    )
    session.add(revision)
    await session.flush()
    _persist_plan(session, revision, plan.items, lesson)
    await session.flush()
    return revision


# --------------------------------------------------------------------------- #
# Création
# --------------------------------------------------------------------------- #


async def start_session(
    session: AsyncSession,
    child_id: uuid.UUID,
    lesson_row: db.Lesson,
    registry: ActivityRegistry,
    now: datetime,
) -> db.RevisionSession:
    """Séance adaptée à la maîtrise actuelle ; reprend une séance en cours de moins de 24 h."""
    if lesson_row.status != "ready":
        raise LessonNotReady
    active = await session.scalar(
        select(db.RevisionSession).where(
            db.RevisionSession.child_id == child_id,
            db.RevisionSession.lesson_id == lesson_row.id,
            db.RevisionSession.status == "active",
            db.RevisionSession.kind != "errors",
        )
    )
    if active is not None:
        if now - active.started_at < STALE_SESSION:
            return active
        active.status = "abandoned"

    lesson = await load_units(session, lesson_row)
    masteries = await load_masteries(session, child_id, lesson)
    seed = new_seed()
    plan = SessionComposer(registry).compose(lesson.units, masteries, now, seed)  # peut lever NothingToReview
    return await _new_session(session, child_id, lesson, plan, seed)


async def start_errors_session(
    session: AsyncSession, origin: db.RevisionSession, registry: ActivityRegistry
) -> db.RevisionSession:
    """« Revoir mes erreurs » : les notions non maîtrisées de la séance d'origine (§8.4)."""
    if origin.status != "completed":
        raise SessionClosed
    lesson_row = await session.get(db.Lesson, origin.lesson_id)
    assert lesson_row is not None
    lesson = await load_units(session, lesson_row)
    rates = session_rates(await load_evidences(session, origin, lesson.id_to_key))
    weak = sorted(
        (k for k, rate in rates.items() if status(rate) is not KnowledgeStatus.MASTERED),
        key=lambda k: (rates[k], -lesson.importance.get(k, 0)),
    )
    seed = new_seed()
    plan = SessionComposer(registry).compose_errors(lesson.units, weak, seed)  # peut lever NothingToReview
    return await _new_session(session, origin.child_id, lesson, plan, seed, parent_session_id=origin.id)


# --------------------------------------------------------------------------- #
# Réponses
# --------------------------------------------------------------------------- #


async def answer(
    session: AsyncSession,
    revision: db.RevisionSession,
    item: db.SessionItem,
    response: dict[str, Any],
    duration_ms: int | None,
    registry: ActivityRegistry,
) -> Grade | None:
    """Corrige et enregistre une réponse. `{"skipped": true}` : activité inconnue de l'application,
    enregistrée sans compter dans la note ni dans la maîtrise (§14.3). Renvoie None dans ce cas."""
    if revision.status != "active":
        raise SessionClosed
    if await session.scalar(select(db.Attempt.id).where(db.Attempt.session_item_id == item.id)):
        raise AlreadyAnswered
    if response == {"skipped": True}:
        session.add(db.Attempt(session_item_id=item.id, response=response, score=0, duration_ms=duration_ms))
        return None

    id_to_key = dict(await _key_map(session, revision.lesson_id))
    activity = activity_of(item, id_to_key)
    grade = registry.for_activity(activity).grade(activity, response)  # peut lever InvalidResponse
    attempt = db.Attempt(
        session_item_id=item.id, response=response, score=round(grade.score, 2), duration_ms=duration_ms
    )
    session.add(attempt)
    await session.flush()
    weight = evidence_weight(activity.type, activity.difficulty, registry)
    key_to_id = {key: knowledge_id for knowledge_id, key in id_to_key.items()}
    for key, result in grade.evidence.items():
        session.add(
            db.AttemptEvidence(
                attempt_id=attempt.id,
                knowledge_id=key_to_id[key],
                result=round(result, 2),
                weight=round(weight, 2),
            )
        )
    return grade


async def _key_map(session: AsyncSession, lesson_id: uuid.UUID) -> list[tuple[uuid.UUID, str]]:
    rows = await session.execute(
        select(db.KnowledgeItem.id, db.KnowledgeItem.key).where(db.KnowledgeItem.lesson_id == lesson_id)
    )
    return [(row[0], row[1]) for row in rows]


async def load_evidences(
    session: AsyncSession, revision: db.RevisionSession, id_to_key: dict[uuid.UUID, str]
) -> list[Evidence]:
    rows = await session.execute(
        select(
            db.AttemptEvidence.knowledge_id,
            db.AttemptEvidence.result,
            db.AttemptEvidence.weight,
            db.SessionItem.activity_type,
            db.SessionItem.block,
        )
        .join(db.Attempt, db.Attempt.id == db.AttemptEvidence.attempt_id)
        .join(db.SessionItem, db.SessionItem.id == db.Attempt.session_item_id)
        .where(db.SessionItem.session_id == revision.id)
        .order_by(db.SessionItem.position)
    )
    return [
        Evidence(id_to_key[k], float(result), float(weight), ActivityCode(kind), block == Block.REPLAY)
        for k, result, weight, kind, block in rows
    ]


# --------------------------------------------------------------------------- #
# Reprise des erreurs et bilan
# --------------------------------------------------------------------------- #


async def add_replay(
    session: AsyncSession, revision: db.RevisionSession, registry: ActivityRegistry
) -> list[db.SessionItem]:
    """Bloc « reprise des erreurs », une seule fois, après les activités principales."""
    if revision.status != "active":
        raise SessionClosed
    items = await session_items(session, revision)
    existing = [i for i in items if i.block == Block.REPLAY]
    if existing or revision.kind == "errors":
        return existing
    attempts = await attempts_by_item(session, revision)
    if any(i.id not in attempts for i in items):
        raise MainNotFinished

    lesson_row = await session.get(db.Lesson, revision.lesson_id)
    assert lesson_row is not None
    lesson = await load_units(session, lesson_row)
    id_to_key = lesson.id_to_key
    evidences = await load_evidences(session, revision, id_to_key)
    previous = [activity_of(i, id_to_key) for i in items]
    planned = SessionComposer(registry).replay(
        lesson.units, evidences, previous, start_position=len(items) + 1, seed=revision.seed
    )
    _persist_plan(session, revision, planned, lesson)
    await session.flush()
    return [i for i in await session_items(session, revision) if i.block == Block.REPLAY]


@dataclass(frozen=True)
class CompletedSession:
    outcome: SessionOutcome
    lesson: LessonUnits


async def complete(session: AsyncSession, revision: db.RevisionSession, now: datetime) -> CompletedSession:
    """Clôture : note sur 10, statut par notion, nouvelles maîtrises et prochaine révision (§9, §10)."""
    if revision.status != "active":
        raise SessionClosed
    lesson_row = await session.get(db.Lesson, revision.lesson_id)
    assert lesson_row is not None
    lesson = await load_units(session, lesson_row)
    items = {i.id: i for i in await session_items(session, revision)}
    main_scores = [
        float(a.score)
        for item_id, a in (await attempts_by_item(session, revision)).items()
        if items[item_id].block != Block.REPLAY and a.response != {"skipped": True}
    ]
    evidences = await load_evidences(session, revision, lesson.id_to_key)
    masteries = await load_masteries(session, revision.child_id, lesson)
    outcome = summarize(main_scores, evidences, masteries, lesson.importance, now)
    await save_masteries(
        session, revision.child_id, lesson, {r.knowledge_id: r.mastery for r in outcome.results}
    )
    revision.status, revision.completed_at = "completed", now
    revision.score_on_10 = Decimal(str(outcome.score_on_10))
    return CompletedSession(outcome, lesson)


# --------------------------------------------------------------------------- #
# Mission du jour (écran 1)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Mission:
    lesson: db.Lesson
    reason: Literal["due", "not_mastered", "latest"]
    estimated_minutes: int


async def mission_of_the_day(
    session: AsyncSession, child_id: uuid.UUID, registry: ActivityRegistry, now: datetime
) -> Mission | None:
    """La révision la plus utile maintenant : notions dues, puis leçon pas encore maîtrisée,
    puis dernière leçon ajoutée ; une leçon sans rien à réviser n'est jamais proposée."""
    composer = SessionComposer(registry)

    async def estimate(lesson_row: db.Lesson) -> int | None:
        lesson = await load_units(session, lesson_row)
        try:
            plan = composer.compose(
                lesson.units, await load_masteries(session, child_id, lesson), now, seed=0
            )
        except NothingToReview:
            return None
        return plan.estimated_minutes

    due = await session.execute(
        select(db.KnowledgeItem.lesson_id, func.min(db.KnowledgeMastery.next_review_at).label("due"))
        .join(db.KnowledgeMastery, db.KnowledgeMastery.knowledge_id == db.KnowledgeItem.id)
        .where(db.KnowledgeMastery.child_id == child_id, db.KnowledgeMastery.next_review_at <= now)
        .group_by(db.KnowledgeItem.lesson_id)
        .order_by("due")
    )
    for lesson_id, _ in due:
        lesson_row = await session.get(db.Lesson, lesson_id)
        if (
            lesson_row is not None
            and lesson_row.status == "ready"
            and (minutes := await estimate(lesson_row))
        ):
            return Mission(lesson_row, "due", minutes)

    recent = await session.scalars(
        select(db.Lesson)
        .where(db.Lesson.child_id == child_id, db.Lesson.status == "ready")
        .order_by(db.Lesson.created_at.desc())
        .limit(20)
    )
    for lesson_row in recent:
        practised = await session.scalar(
            select(func.count())
            .select_from(db.KnowledgeMastery)
            .join(db.KnowledgeItem, db.KnowledgeItem.id == db.KnowledgeMastery.knowledge_id)
            .where(db.KnowledgeMastery.child_id == child_id, db.KnowledgeItem.lesson_id == lesson_row.id)
        )
        if (minutes := await estimate(lesson_row)) is not None:
            return Mission(lesson_row, "not_mastered" if practised else "latest", minutes)
    return None
