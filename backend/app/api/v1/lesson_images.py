"""Images d'une leçon (étapes 27 et 28) : celle de la leçon et celles des notions concrètes.

Le parent les voit, les valide, les refuse ou les fait refaire ; l'enfant ne voit qu'une image
validée. Facultatives : sans elles, la leçon est complète et les jeux en images ne sont pas
proposés. Routes `…/image` : l'image de la leçon ; `…/images/{id}` : n'importe laquelle."""

import asyncio
import uuid
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.ai.factory import AiConfigError
from app.ai.imagegen.factory import image_engine_for
from app.ai.ports import LLMProvider
from app.api.deps import AppSettings, ChildInScope, CurrentParent, DbSession, get_ai_resolver, get_database
from app.api.errors import ApiError
from app.api.v1.children import own_child
from app.api.v1.lessons import ensure_ai_budget
from app.db import models as db_models
from app.domain.illustration import REMARK_MAX, ImageStatus
from app.services import illustration
from app.services.ai_settings import AiResolver
from app.services.illustration import image_path
from app.services.lesson_processing import draw_image, redraw_image

router = APIRouter(tags=["images des leçons"])

IMAGE_NOT_FOUND = ApiError(404, "image_not_found", "Pas d'image pour cette leçon.")


class LessonImageOut(BaseModel):
    status: Literal["generating", "to_review", "approved", "rejected", "failed", "not_needed"]
    alt: str | None = Field(None, description="Ce que montre l'image.")
    remark: str | None = Field(None, description="Remarque du parent pour la refaire.")
    error: str | None = Field(
        None,
        description="Pourquoi l'image n'a pas pu être faite, ou (statut `not_needed`) pourquoi une "
        "image n'aiderait pas à retenir la leçon.",
    )
    url: str | None = Field(None, description="Adresse du fichier (même authentification que l'API).")
    id: uuid.UUID | None = Field(None, description="Pour les routes …/images/{id} (étape 28).")
    knowledge_id: uuid.UUID | None = Field(None, description="La notion montrée ; vide : la leçon.")
    label: str | None = Field(None, description="Nom de la notion montrée.")
    exact: bool = Field(
        False, description="Figure ou schéma dessiné par Ludifun (§5.61), pas par le moteur d'images."
    )


class ImagesOut(BaseModel):
    available: bool = Field(
        description="Le serveur a un moteur d'images, ou Ludifun sait dessiner les figures de la leçon."
    )
    image: LessonImageOut | None = Field(None, description="L'image de la leçon.")
    pictures: list[LessonImageOut] = Field(
        [], description="Images des notions, pour les jeux « apprendre par l'image » (étape 28)."
    )


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
    """L'image de la leçon (pas celles des notions)."""
    row: db_models.LessonImage | None = await db.scalar(
        select(db_models.LessonImage).where(
            db_models.LessonImage.lesson_id == lesson.id, db_models.LessonImage.knowledge_id.is_(None)
        )
    )
    return row


async def _image_by_id(
    db: DbSession, lesson: db_models.Lesson, image_id: uuid.UUID
) -> db_models.LessonImage | None:
    row: db_models.LessonImage | None = await db.scalar(
        select(db_models.LessonImage).where(
            db_models.LessonImage.id == image_id, db_models.LessonImage.lesson_id == lesson.id
        )
    )
    return row


def _out(row: db_models.LessonImage, child_id: uuid.UUID, label: str | None = None) -> LessonImageOut:
    has_file = row.file_name is not None and row.status not in (
        ImageStatus.GENERATING.value,
        ImageStatus.NOT_NEEDED.value,
    )
    base = f"/v1/children/{child_id}/lessons/{row.lesson_id}"
    file = f"{base}/image/file" if row.knowledge_id is None else f"{base}/images/{row.id}/file"
    return LessonImageOut(
        status=row.status,
        alt=row.alt,
        remark=row.remark,
        error=row.error if row.status in (ImageStatus.FAILED.value, ImageStatus.NOT_NEEDED.value) else None,
        url=file if has_file else None,
        id=row.id,
        knowledge_id=row.knowledge_id,
        label=label,
        exact=row.engine == illustration.CODE_ENGINE,
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
    """L'image de la leçon et celles des notions, quel que soit leur statut."""
    child = await own_child(db, parent, child_id)
    lesson = await _lesson(db, child, lesson_id)
    rows = (
        await db.execute(
            select(db_models.LessonImage, db_models.KnowledgeItem.label)
            .outerjoin(
                db_models.KnowledgeItem, db_models.KnowledgeItem.id == db_models.LessonImage.knowledge_id
            )
            .where(db_models.LessonImage.lesson_id == lesson.id)
            .order_by(db_models.KnowledgeItem.position.nulls_first())
        )
    ).all()
    cover = next((row for row, _ in rows if row.knowledge_id is None), None)
    return ImagesOut(
        available=image_engine_for(settings) is not None or await illustration.can_draw(db, lesson.id),
        image=_out(cover, child.id) if cover else None,
        pictures=[_out(row, child.id, label) for row, label in rows if row.knowledge_id is not None],
    )


@router.get("/children/{child_id}/lessons/{lesson_id}/image/file")
async def get_image_file(
    child_id: uuid.UUID, lesson_id: uuid.UUID, parent: CurrentParent, db: DbSession, settings: AppSettings
) -> Response:
    """Le fichier de l'image de la leçon, quel que soit son statut : le parent le voit avant de
    le valider."""
    child = await own_child(db, parent, child_id)
    return await _file(await _image(db, await _lesson(db, child, lesson_id)), settings)


@router.get("/children/{child_id}/lessons/{lesson_id}/images/{image_id}/file")
async def get_any_image_file(
    child_id: uuid.UUID,
    lesson_id: uuid.UUID,
    image_id: uuid.UUID,
    parent: CurrentParent,
    db: DbSession,
    settings: AppSettings,
) -> Response:
    """Le fichier d'une image de la leçon ou d'une notion, quel que soit son statut."""
    child = await own_child(db, parent, child_id)
    return await _file(await _image_by_id(db, await _lesson(db, child, lesson_id), image_id), settings)


async def _decide(
    db: DbSession, child: db_models.Child, row: db_models.LessonImage | None, decision: ImageStatus
) -> LessonImageOut:
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
    child = await own_child(db, parent, child_id)
    return await _decide(
        db, child, await _image(db, await _lesson(db, child, lesson_id)), ImageStatus.APPROVED
    )


@router.post("/children/{child_id}/lessons/{lesson_id}/image/reject")
async def reject_image(
    child_id: uuid.UUID, lesson_id: uuid.UUID, parent: CurrentParent, db: DbSession
) -> LessonImageOut:
    """L'enfant ne la verra pas ; le parent peut demander de la refaire."""
    child = await own_child(db, parent, child_id)
    return await _decide(
        db, child, await _image(db, await _lesson(db, child, lesson_id)), ImageStatus.REJECTED
    )


async def _decide_by_id(
    child_id: uuid.UUID,
    lesson_id: uuid.UUID,
    image_id: uuid.UUID,
    parent: CurrentParent,
    db: DbSession,
    decision: ImageStatus,
) -> LessonImageOut:
    child = await own_child(db, parent, child_id)
    row = await _image_by_id(db, await _lesson(db, child, lesson_id), image_id)
    return await _decide(db, child, row, decision)


@router.post("/children/{child_id}/lessons/{lesson_id}/images/{image_id}/approve")
async def approve_any_image(
    child_id: uuid.UUID, lesson_id: uuid.UUID, image_id: uuid.UUID, parent: CurrentParent, db: DbSession
) -> LessonImageOut:
    """L'enfant la voit ; l'image d'une notion sert aux jeux « apprendre par l'image »."""
    return await _decide_by_id(child_id, lesson_id, image_id, parent, db, ImageStatus.APPROVED)


@router.post("/children/{child_id}/lessons/{lesson_id}/images/{image_id}/reject")
async def reject_any_image(
    child_id: uuid.UUID, lesson_id: uuid.UUID, image_id: uuid.UUID, parent: CurrentParent, db: DbSession
) -> LessonImageOut:
    """L'enfant ne la voit pas et aucun jeu ne s'en sert ; le parent peut la faire refaire."""
    return await _decide_by_id(child_id, lesson_id, image_id, parent, db, ImageStatus.REJECTED)


async def _redo(
    db: DbSession,
    settings: AppSettings,
    resolver: AiResolver,
    child: db_models.Child,
    lesson: db_models.Lesson,
    knowledge_id: uuid.UUID | None,
    remark: str | None,
) -> tuple[db_models.LessonImage, LLMProvider | None, bool]:
    """L'image remise « en préparation », l'IA de l'enfant (aucune si le code dessine seul) et
    s'il faut lancer le dessin (non : déjà en préparation, un double appui ne relance rien)."""
    engine = image_engine_for(settings) is not None
    drawable = await illustration.can_draw(db, lesson.id, knowledge_id, remark)
    if not engine and not drawable:
        raise ApiError(503, "images_unavailable", "Le serveur n'a pas de moteur d'images.")
    existing = await illustration.image_of(db, lesson.id, knowledge_id)
    if existing is not None and existing.status == ImageStatus.GENERATING:
        return existing, None, False
    llm: LLMProvider | None = None
    if engine:
        try:
            await ensure_ai_budget(db, settings)
            _, llm = await resolver.for_child(db, child)
        except AiConfigError as exc:
            if not drawable:
                raise ApiError(
                    503, "ai_not_configured", "L'IA choisie n'est pas prête : vérifiez son réglage."
                ) from exc
        except ApiError:
            if not drawable:
                raise
    row = await illustration.start(db, lesson.id, remark, knowledge_id)
    await db.commit()
    return row, llm, True


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
    """Une nouvelle image de la leçon (ou une première, même jugée « pas utile »), avec la
    remarque du parent ; elle attendra à nouveau sa validation. Préparée en arrière-plan :
    interroger GET …/image."""
    child = await own_child(db, parent, child_id)
    lesson = await _lesson(db, child, lesson_id)
    row, llm, run = await _redo(db, settings, resolver, child, lesson, None, body.remark)
    if run:
        background.add_task(redraw_image, get_database(request), llm, settings, row.id)
    return _out(row, child.id)


@router.post(
    "/children/{child_id}/lessons/{lesson_id}/images/{image_id}/redo", status_code=status.HTTP_202_ACCEPTED
)
async def redo_any_image(
    child_id: uuid.UUID,
    lesson_id: uuid.UUID,
    image_id: uuid.UUID,
    body: RedoIn,
    request: Request,
    background: BackgroundTasks,
    parent: CurrentParent,
    db: DbSession,
    settings: AppSettings,
    resolver: Annotated[AiResolver, Depends(get_ai_resolver)],
) -> LessonImageOut:
    """Refaire une image (de la leçon ou d'une notion) avec la remarque du parent."""
    child = await own_child(db, parent, child_id)
    lesson = await _lesson(db, child, lesson_id)
    current = await _image_by_id(db, lesson, image_id)
    if current is None:
        raise IMAGE_NOT_FOUND
    row, llm, run = await _redo(db, settings, resolver, child, lesson, current.knowledge_id, body.remark)
    if run:
        background.add_task(redraw_image, get_database(request), llm, settings, row.id)
    return _out(row, child.id)


@router.post("/children/{child_id}/lessons/{lesson_id}/images/prepare", status_code=status.HTTP_202_ACCEPTED)
async def prepare_images(
    child_id: uuid.UUID,
    lesson_id: uuid.UUID,
    request: Request,
    background: BackgroundTasks,
    parent: CurrentParent,
    db: DbSession,
    settings: AppSettings,
    resolver: Annotated[AiResolver, Depends(get_ai_resolver)],
) -> LessonImageOut:
    """Comme après l'analyse : l'IA dit si une image aide et quelles notions se dessinent, puis
    tout est dessiné (pour une leçon analysée avant les images, ou pour tout reprendre)."""
    child = await own_child(db, parent, child_id)
    lesson = await _lesson(db, child, lesson_id)
    row, llm, run = await _redo(db, settings, resolver, child, lesson, None, None)
    if run:
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


@router.get("/lessons/{lesson_id}/images/{image_id}")
async def get_child_picture(
    lesson_id: uuid.UUID, image_id: uuid.UUID, child: ChildInScope, db: DbSession, settings: AppSettings
) -> Response:
    """Une image de la leçon ou d'une notion (jeux en images), seulement si le parent l'a validée."""
    row = await _image_by_id(db, await _lesson(db, child, lesson_id), image_id)
    if row is None or row.status != ImageStatus.APPROVED:
        raise IMAGE_NOT_FOUND
    return await _file(row, settings)
