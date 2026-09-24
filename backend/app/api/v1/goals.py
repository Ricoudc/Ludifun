"""Espace parent : contrôles à venir et plan de révision (étape 16)."""

import uuid
from datetime import date, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import select

from app import clock
from app.api.deps import AppSettings, CurrentParent, DbSession
from app.api.errors import ApiError
from app.api.v1.children import own_child
from app.db.models import Exam, Lesson
from app.domain.planning import PlanDay
from app.services import goals

router = APIRouter(tags=["objectifs"])

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class ExamIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title = Field(description="« Contrôle d'histoire », « Évaluation fractions »…")
    exam_date: date
    lesson_ids: list[uuid.UUID] = Field(min_length=1, max_length=goals.MAX_EXAM_LESSONS)


class PlanDayOut(BaseModel):
    day: date
    focus: str
    label: str
    done: bool


class ExamOut(BaseModel):
    id: uuid.UUID
    title: str
    exam_date: date
    lesson_ids: list[uuid.UUID]
    plan: list[PlanDayOut] = Field(description="Étapes à venir, recalculées chaque jour.")


def plan_out(plan: list[PlanDay]) -> list[PlanDayOut]:
    return [PlanDayOut(day=p.day, focus=p.focus.value, label=p.label, done=p.done) for p in plan]


async def exam_out(db: DbSession, exam: Exam, tz: ZoneInfo) -> ExamOut:
    return ExamOut(
        id=exam.id,
        title=exam.title,
        exam_date=exam.exam_date,
        lesson_ids=exam.lesson_ids,
        plan=plan_out(await goals.exam_plan(db, exam, clock.now(), tz)),
    )


@router.get("/children/{child_id}/exams")
async def list_exams(
    child_id: uuid.UUID, parent: CurrentParent, db: DbSession, settings: AppSettings
) -> list[ExamOut]:
    child = await own_child(db, parent, child_id)
    tz = ZoneInfo(settings.family_timezone)
    exams = await goals.active_exams(db, child.id, goals.local_day(clock.now(), tz))
    return [await exam_out(db, exam, tz) for exam in exams]


@router.post("/children/{child_id}/exams", status_code=status.HTTP_201_CREATED)
async def create_exam(
    child_id: uuid.UUID, body: ExamIn, parent: CurrentParent, db: DbSession, settings: AppSettings
) -> ExamOut:
    """Un contrôle à venir : chaque jour jusqu'à la veille, la mission de l'enfant suit le plan."""
    child = await own_child(db, parent, child_id)
    tz = ZoneInfo(settings.family_timezone)
    today = goals.local_day(clock.now(), tz)
    if not today < body.exam_date <= today + timedelta(days=goals.MAX_DAYS_AHEAD):
        raise ApiError(422, "invalid_exam_date", "Choisis une date entre demain et dans deux mois.")
    lesson_ids = list(dict.fromkeys(body.lesson_ids))
    found = set(
        await db.scalars(
            select(Lesson.id).where(
                Lesson.id.in_(lesson_ids), Lesson.child_id == child.id, Lesson.status == "ready"
            )
        )
    )
    if found != set(lesson_ids):
        raise ApiError(422, "invalid_lessons", "Choisis des leçons prêtes de cet enfant.")
    if len(await goals.active_exams(db, child.id, today)) >= goals.MAX_ACTIVE_EXAMS:
        raise ApiError(409, "too_many_exams", "Il y a déjà 5 contrôles à venir.")
    exam = Exam(
        child_id=child.id,
        title=body.title,
        exam_date=body.exam_date,
        lesson_ids=lesson_ids,
        created_at=clock.now(),
    )
    db.add(exam)
    await db.commit()
    return await exam_out(db, exam, tz)


@router.delete("/children/{child_id}/exams/{exam_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exam(
    child_id: uuid.UUID, exam_id: uuid.UUID, parent: CurrentParent, db: DbSession
) -> Response:
    child = await own_child(db, parent, child_id)
    exam = await db.scalar(select(Exam).where(Exam.id == exam_id, Exam.child_id == child.id))
    if exam is None:
        raise ApiError(404, "exam_not_found", "Contrôle introuvable.")
    await db.delete(exam)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
