"""Ressources des sites de confiance (étape 30) : exercices MathALÉA, quiz Vikidia, vidéos et
quiz Lumni, ouverts dans la visionneuse de l'application.

L'enfant voit celles que le parent n'a pas masquées et envoie le score d'un exercice noté ; le
parent les voit toutes, avec les scores, les masque ou les fait chercher pour une leçon déjà
analysée. Seulement si le parent a permis les sites éducatifs de confiance."""

import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app import clock
from app.api.deps import AppSettings, ChildInScope, CurrentParent, DbSession, get_database
from app.api.errors import ApiError
from app.api.v1.children import own_child
from app.api.v1.schemas_learning import LessonResourceOut, ResourceScoreOut
from app.db import models as db_models
from app.domain.resources import LICENCES, Provider
from app.services import external_resources

router = APIRouter(tags=["ressources des sites de confiance"])

RESOURCE_NOT_FOUND = ApiError(404, "resource_not_found", "Ressource introuvable.")


class ParentResourceOut(LessonResourceOut):
    hidden: bool
    attempts: int = Field(description="Exercices notés terminés par l'enfant.")
    last_done_at: datetime | None = None


class ResourcesOut(BaseModel):
    available: bool = Field(
        description="Le parent a permis les sites de confiance et le serveur les propose."
    )
    resources: list[ParentResourceOut] = []


class ResultIn(BaseModel):
    """Score renvoyé par l'exercice (MathALÉA) à la fin."""

    model_config = ConfigDict(extra="forbid")

    correct: int = Field(ge=0, le=100)
    total: int = Field(ge=1, le=100)

    @model_validator(mode="after")
    def _coherent(self) -> "ResultIn":
        if self.correct > self.total:
            raise ValueError("plus de bonnes réponses que de questions")
        return self


def resource_out(row: db_models.LessonResource) -> LessonResourceOut:
    best = (
        ResourceScoreOut(correct=row.best_correct, total=row.best_total)
        if row.best_correct is not None and row.best_total
        else None
    )
    return LessonResourceOut(
        id=row.id,
        provider=row.provider,
        kind=row.kind,
        title=row.title,
        url=row.url,
        licence=LICENCES[Provider(row.provider)],
        best=best,
    )


async def visible_resources(db: DbSession, lesson_id: uuid.UUID) -> list[LessonResourceOut]:
    rows = await db.scalars(
        select(db_models.LessonResource)
        .where(db_models.LessonResource.lesson_id == lesson_id, db_models.LessonResource.hidden.is_(False))
        .order_by(db_models.LessonResource.position)
    )
    return [resource_out(r) for r in rows]


async def _lesson(db: DbSession, child: db_models.Child, lesson_id: uuid.UUID) -> db_models.Lesson:
    lesson = await db.scalar(
        select(db_models.Lesson).where(
            db_models.Lesson.id == lesson_id, db_models.Lesson.child_id == child.id
        )
    )
    if lesson is None or lesson.status != "ready":
        raise ApiError(404, "lesson_not_found", "Leçon introuvable.")
    return lesson


async def _resource(
    db: DbSession, lesson: db_models.Lesson, resource_id: uuid.UUID
) -> db_models.LessonResource:
    row = await db.scalar(
        select(db_models.LessonResource).where(
            db_models.LessonResource.id == resource_id, db_models.LessonResource.lesson_id == lesson.id
        )
    )
    if row is None:
        raise RESOURCE_NOT_FOUND
    return row


async def _allowed(db: DbSession, settings: AppSettings, child: db_models.Child) -> bool:
    family = await db.get(db_models.Family, child.family_id)
    return bool(settings.resources and family is not None and family.web_sources)


# --------------------------------------------------------------------------- #
# Enfant
# --------------------------------------------------------------------------- #


@router.post("/lessons/{lesson_id}/resources/{resource_id}/result")
async def post_result(
    lesson_id: uuid.UUID, resource_id: uuid.UUID, body: ResultIn, child: ChildInScope, db: DbSession
) -> LessonResourceOut:
    """Score d'un exercice noté, à la fin ; le meilleur est gardé pour le parent. Il ne change
    pas la maîtrise des notions (l'exercice n'est pas corrigé par Ludifun)."""
    row = await _resource(db, await _lesson(db, child, lesson_id), resource_id)
    if row.hidden:
        raise RESOURCE_NOT_FOUND
    row.attempts += 1
    row.last_done_at = clock.now()
    best = (row.best_correct or 0) / row.best_total if row.best_total else -1.0
    if body.correct / body.total >= best:
        row.best_correct, row.best_total = body.correct, body.total
    await db.commit()
    return resource_out(row)


# --------------------------------------------------------------------------- #
# Espace parent
# --------------------------------------------------------------------------- #


def _parent_out(row: db_models.LessonResource) -> ParentResourceOut:
    return ParentResourceOut(
        **resource_out(row).model_dump(),
        hidden=row.hidden,
        attempts=row.attempts,
        last_done_at=row.last_done_at,
    )


@router.get("/children/{child_id}/lessons/{lesson_id}/resources")
async def get_resources(
    child_id: uuid.UUID, lesson_id: uuid.UUID, parent: CurrentParent, db: DbSession, settings: AppSettings
) -> ResourcesOut:
    child = await own_child(db, parent, child_id)
    lesson = await _lesson(db, child, lesson_id)
    rows = await db.scalars(
        select(db_models.LessonResource)
        .where(db_models.LessonResource.lesson_id == lesson.id)
        .order_by(db_models.LessonResource.position)
    )
    return ResourcesOut(
        available=await _allowed(db, settings, child), resources=[_parent_out(r) for r in rows]
    )


async def _set_hidden(
    child_id: uuid.UUID,
    lesson_id: uuid.UUID,
    resource_id: uuid.UUID,
    parent: CurrentParent,
    db: DbSession,
    hidden: bool,
) -> ParentResourceOut:
    child = await own_child(db, parent, child_id)
    row = await _resource(db, await _lesson(db, child, lesson_id), resource_id)
    row.hidden = hidden
    await db.commit()
    return _parent_out(row)


@router.post("/children/{child_id}/lessons/{lesson_id}/resources/{resource_id}/hide")
async def hide_resource(
    child_id: uuid.UUID, lesson_id: uuid.UUID, resource_id: uuid.UUID, parent: CurrentParent, db: DbSession
) -> ParentResourceOut:
    """L'enfant ne la voit plus."""
    return await _set_hidden(child_id, lesson_id, resource_id, parent, db, True)


@router.post("/children/{child_id}/lessons/{lesson_id}/resources/{resource_id}/show")
async def show_resource(
    child_id: uuid.UUID, lesson_id: uuid.UUID, resource_id: uuid.UUID, parent: CurrentParent, db: DbSession
) -> ParentResourceOut:
    return await _set_hidden(child_id, lesson_id, resource_id, parent, db, False)


@router.post(
    "/children/{child_id}/lessons/{lesson_id}/resources/prepare", status_code=status.HTTP_202_ACCEPTED
)
async def prepare_resources(
    child_id: uuid.UUID,
    lesson_id: uuid.UUID,
    request: Request,
    background: BackgroundTasks,
    parent: CurrentParent,
    db: DbSession,
    settings: AppSettings,
) -> ResourcesOut:
    """Cherche les ressources d'une leçon déjà analysée (en arrière-plan : relire GET …/resources)."""
    child = await own_child(db, parent, child_id)
    lesson = await _lesson(db, child, lesson_id)
    if not await _allowed(db, settings, child):
        raise ApiError(
            409,
            "resources_not_allowed",
            "Autorisez d'abord les sites éducatifs de confiance (Mon compte → Intelligence artificielle).",
        )
    background.add_task(external_resources.prepare, get_database(request), settings, lesson.id)
    return await get_resources(child_id, lesson_id, parent, db, settings)
