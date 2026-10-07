"""Image d'une leçon (étape 27) : le parent la voit, la valide, la refuse ou la fait refaire ;
l'enfant ne voit qu'une image validée. L'image est facultative : aucune question n'en dépend."""

import asyncio
import uuid
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.ai.factory import AiConfigError
from app.ai.imagegen.factory import image_engine_for
from app.api.deps import AppSettings, ChildInScope, CurrentParent, DbSession, get_ai_resolver, get_database
from app.api.errors import ApiError
from app.api.v1.children import own_child
from app.api.v1.lessons import ensure_ai_budget
from app.db import models as db_models
from app.domain.illustration import REMARK_MAX, ImageStatus
from app.services import illustration
from app.services.ai_settings import AiResolver
from app.services.illustration import image_path
from app.services.lesson_processing import draw_image

router = APIRouter(tags=["images des leçons"])

IMAGE_NOT_FOUND = ApiError(404, "image_not_found", "Pas d'image pour cette leçon.")


class LessonImageOut(BaseModel):
    status: Literal["generating", "to_review", "approved", "rejected", "failed"]
    alt: str | None = Field(None, description="Ce que montre l'image.")
    remark: str | None = Field(None, description="Remarque du parent pour la refaire.")
    error: str | None = Field(None, description="Pourquoi l'image n'a pas pu être faite.")
    url: str | None = Field(None, description="Adresse du fichier (même authentification que l'API).")


class ImagesOut(BaseModel):
    available: bool = Field(description="Le serveur a un moteur d'images.")
    image: LessonImageOut | None = None


class RedoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    remark: str | None = Field(None, max_length=REMARK_MAX)


async def _lesson(db: DbSession, child: db_models.Child, lesson_id: uuid.UUID) -> db_models.Lesson:
    lesson = await db.scalar(
        select(db_models.Lesson).where(
            db_models.Lesson.id == lesson_id, db_models.Lesson.child_id == child.id
        )
    )
    if lesson is None or lesson.status != "ready":
        raise ApiError(404, "lesson_not_found", "Leçon introuvable.")
    return lesson


async def _image(db: DbSession, lesson: db_models.Lesson) -> db_models.LessonImage | None:
    row: db_models.LessonImage | None = await db.scalar(
        select(db_models.LessonImage).where(db_models.LessonImage.lesson_id == lesson.id)
    )
    return row


def _out(row: db_models.LessonImage, child_id: uuid.UUID) -> LessonImageOut:
    has_file = row.file_name is not None and row.status != ImageStatus.GENERATING.value
    return LessonImageOut(
        status=row.status,
        alt=row.alt,
        remark=row.remark,
        error=row.error if row.status == ImageStatus.FAILED.value else None,
        url=f"/v1/children/{child_id}/lessons/{row.lesson_id}/image/file" if has_file else None,
    )


async def _file(row: db_models.LessonImage | None, settings: AppSettings) -> Response:
    path: Path | None = image_path(settings, row) if row is not None else None
    if row is None or path is None:
        raise IMAGE_NOT_FOUND
    data = await asyncio.to_thread(path.read_bytes)
    # Image privée de la famille : jamais gardée par un intermédiaire.
    return Response(
        data, media_type=row.media_type or "image/png", headers={"Cache-Control": "private, max-age=3600"}
    )


# --------------------------------------------------------------------------- #
# Espace parent
# --------------------------------------------------------------------------- #


@router.get("/children/{child_id}/lessons/{lesson_id}/image")
async def get_image(
    child_id: uuid.UUID, lesson_id: uuid.UUID, parent: CurrentParent, db: DbSession, settings: AppSettings
) -> ImagesOut:
    child = await own_child(db, parent, child_id)
    row = await _image(db, await _lesson(db, child, lesson_id))
    return ImagesOut(
        available=image_engine_for(settings) is not None, image=_out(row, child.id) if row else None
    )


@router.get("/children/{child_id}/lessons/{lesson_id}/image/file")
async def get_image_file(
    child_id: uuid.UUID, lesson_id: uuid.UUID, parent: CurrentParent, db: DbSession, settings: AppSettings
) -> Response:
    """Le fichier, quel que soit son statut : le parent le voit avant de le valider."""
    child = await own_child(db, parent, child_id)
    return await _file(await _image(db, await _lesson(db, child, lesson_id)), settings)


async def _decide(
    child_id: uuid.UUID, lesson_id: uuid.UUID, parent: CurrentParent, db: DbSession, decision: ImageStatus
) -> LessonImageOut:
    child = await own_child(db, parent, child_id)
    row = await _image(db, await _lesson(db, child, lesson_id))
    if row is None or row.file_name is None:
        raise IMAGE_NOT_FOUND
    if row.status not in (ImageStatus.TO_REVIEW, ImageStatus.APPROVED, ImageStatus.REJECTED):
        raise ApiError(409, "image_not_ready", "L'image n'est pas prête.")
    row.status = decision.value
    await db.commit()
    return _out(row, child.id)


@router.post("/children/{child_id}/lessons/{lesson_id}/image/approve")
async def approve_image(
    child_id: uuid.UUID, lesson_id: uuid.UUID, parent: CurrentParent, db: DbSession
) -> LessonImageOut:
    """L'enfant verra l'image avec sa leçon."""
    return await _decide(child_id, lesson_id, parent, db, ImageStatus.APPROVED)


@router.post("/children/{child_id}/lessons/{lesson_id}/image/reject")
async def reject_image(
    child_id: uuid.UUID, lesson_id: uuid.UUID, parent: CurrentParent, db: DbSession
) -> LessonImageOut:
    """L'enfant ne la verra pas ; le parent peut demander de la refaire."""
    return await _decide(child_id, lesson_id, parent, db, ImageStatus.REJECTED)


@router.post("/children/{child_id}/lessons/{lesson_id}/image/redo", status_code=status.HTTP_202_ACCEPTED)
async def redo_image(
    child_id: uuid.UUID,
    lesson_id: uuid.UUID,
    body: RedoIn,
    request: Request,
    background: BackgroundTasks,
    parent: CurrentParent,
    db: DbSession,
    settings: AppSettings,
    resolver: Annotated[AiResolver, Depends(get_ai_resolver)],
) -> LessonImageOut:
    """Une nouvelle image (ou une première), avec la remarque du parent ; elle attendra à nouveau
    sa validation. Préparée en arrière-plan : interroger GET …/image."""
    child = await own_child(db, parent, child_id)
    lesson = await _lesson(db, child, lesson_id)
    if image_engine_for(settings) is None:
        raise ApiError(503, "images_unavailable", "Le serveur n'a pas de moteur d'images.")
    row = await _image(db, lesson)
    if row is not None and row.status == ImageStatus.GENERATING:
        return _out(row, child.id)  # déjà en préparation : un double appui ne relance rien
    await ensure_ai_budget(db, settings)
    try:
        _, llm = await resolver.for_child(db, child)
    except AiConfigError as exc:
        raise ApiError(
            503, "ai_not_configured", "L'IA choisie n'est pas prête : vérifiez son réglage."
        ) from exc
    row = await illustration.start(db, lesson.id, body.remark)
    await db.commit()
    background.add_task(draw_image, get_database(request), llm, settings, lesson.id)
    return _out(row, child.id)


# --------------------------------------------------------------------------- #
# Enfant
# --------------------------------------------------------------------------- #


@router.get("/lessons/{lesson_id}/image")
async def get_child_image(
    lesson_id: uuid.UUID, child: ChildInScope, db: DbSession, settings: AppSettings
) -> Response:
    """L'image de la leçon, seulement si le parent l'a validée."""
    row = await _image(db, await _lesson(db, child, lesson_id))
    if row is None or row.status != ImageStatus.APPROVED:
        raise IMAGE_NOT_FOUND
    return await _file(row, settings)
