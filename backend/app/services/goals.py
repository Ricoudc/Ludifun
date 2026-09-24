"""Objectifs du parent en base : temps quotidien, matière prioritaire, contrôles et plan du jour
(spécification technique §5.8, §5.9)."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as db
from app.domain.planning import PlanDay, core_size, revision_plan, today_step
from app.services.learning import SessionOptions
from app.services.lesson_store import load_masteries, load_units

MAX_ACTIVE_EXAMS = 5
MAX_EXAM_LESSONS = 6
MAX_DAYS_AHEAD = 60


def local_day(moment: datetime, tz: ZoneInfo) -> date:
    return moment.astimezone(tz).date()


async def active_exams(session: AsyncSession, child_id: uuid.UUID, today: date) -> list[db.Exam]:
    """Contrôles d'aujourd'hui ou à venir, le plus proche d'abord."""
    return list(
        await session.scalars(
            select(db.Exam)
            .where(db.Exam.child_id == child_id, db.Exam.exam_date >= today)
            .order_by(db.Exam.exam_date, db.Exam.created_at)
        )
    )


async def revised_days(session: AsyncSession, exam: db.Exam, tz: ZoneInfo) -> list[date]:
    """Jours où une séance sur les leçons du contrôle a été terminée depuis sa création."""
    completed = await session.scalars(
        select(db.RevisionSession.completed_at).where(
            db.RevisionSession.child_id == exam.child_id,
            db.RevisionSession.lesson_id.in_(exam.lesson_ids),
            db.RevisionSession.status == "completed",
            db.RevisionSession.completed_at >= exam.created_at,
        )
    )
    return sorted({local_day(at, tz) for at in completed if at is not None})


async def exam_plan(session: AsyncSession, exam: db.Exam, now: datetime, tz: ZoneInfo) -> list[PlanDay]:
    return revision_plan(local_day(now, tz), exam.exam_date, await revised_days(session, exam, tz))


async def _weakest_lesson(session: AsyncSession, exam: db.Exam) -> db.Lesson | None:
    """La leçon du contrôle la moins bien maîtrisée (score moyen, notions jamais vues à 0)."""
    best: tuple[float, db.Lesson] | None = None
    for position, lesson_id in enumerate(exam.lesson_ids):
        lesson = await session.get(db.Lesson, lesson_id)
        if lesson is None or lesson.status != "ready" or lesson.child_id != exam.child_id:
            continue
        units = await load_units(session, lesson)
        masteries = await load_masteries(session, exam.child_id, units)
        average = sum(m.score for m in masteries.values()) / max(1, len(units.units))
        key = average + position / 1000  # à égalité, l'ordre choisi par le parent
        if best is None or key < best[0]:
            best = (key, lesson)
    return best[1] if best else None


@dataclass(frozen=True)
class TodayPlan:
    exam: db.Exam
    step: PlanDay
    lesson: db.Lesson


async def today_plan(
    session: AsyncSession, child_id: uuid.UUID, now: datetime, tz: ZoneInfo
) -> TodayPlan | None:
    """L'étape d'aujourd'hui du contrôle le plus proche, si elle n'est pas encore faite."""
    today = local_day(now, tz)
    for exam in await active_exams(session, child_id, today):
        step = today_step(await exam_plan(session, exam, now, tz), today)
        if step is None or step.done:
            continue
        lesson = await _weakest_lesson(session, exam)
        if lesson is not None:
            return TodayPlan(exam, step, lesson)
    return None


async def session_options(
    session: AsyncSession, child: db.Child, lesson_id: uuid.UUID, now: datetime, tz: ZoneInfo
) -> SessionOptions:
    """Durée selon le temps quotidien ; étape du plan si la leçon fait partie du contrôle du jour."""
    plan = await today_plan(session, child.id, now, tz)
    in_plan = plan is not None and lesson_id in plan.exam.lesson_ids
    return SessionOptions(core_size(child.daily_minutes), plan.step.focus if plan and in_plan else None)
