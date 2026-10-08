"""Analyse d'une leçon en arrière-plan : le statut avance en base à chaque étape (écran 3)."""

import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import ColumnElement, select, update

from app.ai.imagegen.factory import image_engine_for
from app.ai.ports import LLMProvider, OcrProvider, PageImage
from app.config import Settings
from app.db.base import Database
from app.db.models import Child, Lesson, LessonImage
from app.domain.activities.registry import ActivityRegistry
from app.services import external_resources, illustration, reading_check, sourced_help, sourced_practice
from app.services.lesson_pipeline import FailureReason, LessonPipeline, LessonStatus, PipelineResult
from app.services.lesson_store import save_pipeline_result
from app.services.live_calls import LIVE

logger = logging.getLogger("ludifun.lessons")


async def process_lesson(
    database: Database,
    ocr: OcrProvider,
    llm: LLMProvider,
    registry: ActivityRegistry,
    settings: Settings,
    lesson_id: uuid.UUID,
    pages: Sequence[PageImage] = (),
    text: str | None = None,
) -> None:
    """Les photos ne vivent qu'en mémoire, le temps de cette fonction (§15)."""

    async def on_status(status: LessonStatus) -> None:
        async with database.sessionmaker() as session:
            await session.execute(update(Lesson).where(Lesson.id == lesson_id).values(status=status.value))
            await session.commit()

    async with database.sessionmaker() as session:
        pupil_grade = await session.scalar(
            select(Child.grade).join(Lesson, Lesson.child_id == Child.id).where(Lesson.id == lesson_id)
        )
    check = None
    if pages:  # une photo : ses dates peuvent être comparées à des sources (étape 24c)
        async with database.sessionmaker() as session:
            if await sourced_help.web_sources_allowed(session, settings, lesson_id):
                check = reading_check.for_settings(settings, database)
    pipeline = LessonPipeline(
        ocr,
        llm,
        registry,
        max_chars=settings.max_lesson_chars,
        on_status=on_status,
        on_call=lambda stage, model: LIVE.track(lesson_id, stage, model),
        reading_check=check,
        pupil_grade=pupil_grade,
    )
    try:
        result = await pipeline.run(pages, text)
    except Exception:  # un bug ne doit pas laisser la leçon « en cours » pour toujours
        logger.exception("Analyse de la leçon %s interrompue", lesson_id)
        result = PipelineResult(failure_reason=FailureReason.AI_ERROR)

    try:
        async with database.sessionmaker() as session:
            lesson = await session.get(Lesson, lesson_id)
            if lesson is not None:  # sinon : supprimée pendant l'analyse
                await save_pipeline_result(session, lesson, result)
                await session.commit()
    except Exception:  # sinon l'écran 3 attendrait jusqu'au prochain redémarrage du serveur
        logger.exception("Leçon %s : enregistrement de l'analyse impossible", lesson_id)
        async with database.sessionmaker() as session:
            failed = {"status": "failed", "failure_reason": "ai_error"}
            await session.execute(update(Lesson).where(Lesson.id == lesson_id).values(**failed))
            await session.commit()
    LIVE.forget(lesson_id)  # la trace est maintenant dans ai_runs
    try:  # aide sourcée (étape 24b) : leçon déjà prête, un échec ne la touche pas
        await sourced_help.prepare(database, llm, settings, lesson_id)
    except Exception:
        logger.exception("Leçon %s : aide sourcée non préparée", lesson_id)
    try:  # exercices tirés des sites de confiance (étape 29) : même autorisation du parent
        await sourced_practice.prepare(database, llm, settings, lesson_id)
    except Exception:
        logger.exception("Leçon %s : exercices des sources non préparés", lesson_id)
    try:  # ressources des sites de confiance (étape 30) : MathALÉA, Vikidia, Lumni
        await external_resources.prepare(database, settings, lesson_id)
    except Exception:
        logger.exception("Leçon %s : ressources des sites de confiance non préparées", lesson_id)
    await prepare_image(database, llm, settings, lesson_id)


async def prepare_image(
    database: Database, llm: LLMProvider, settings: Settings, lesson_id: uuid.UUID, remark: str | None = None
) -> None:
    """Image de la leçon (étape 27), après tout le reste : la leçon est déjà prête, l'enfant
    peut réviser pendant que l'image se prépare ; elle attendra la validation du parent."""
    if image_engine_for(settings) is None:
        return
    try:
        async with database.sessionmaker() as session:
            lesson = await session.get(Lesson, lesson_id)
            if lesson is None or lesson.status != "ready":
                return
            await illustration.start(session, lesson_id, remark)
            await session.commit()
    except Exception:
        logger.exception("Leçon %s : image non préparée", lesson_id)
        return
    await draw_image(database, llm, settings, lesson_id)


async def draw_image(database: Database, llm: LLMProvider, settings: Settings, lesson_id: uuid.UUID) -> None:
    """Images de la leçon (celle de la leçon déjà « en préparation ») ; un échec ne touche
    jamais la leçon."""
    engine = image_engine_for(settings)
    if engine is None:
        return
    try:
        await illustration.illustrate_lesson(database, llm, engine, settings, lesson_id)
    except Exception:  # un bug ne doit laisser ni la leçon ni une image « en préparation »
        logger.exception("Leçon %s : images non préparées", lesson_id)
        await _unstick(database, LessonImage.lesson_id == lesson_id)


async def redraw_image(database: Database, llm: LLMProvider, settings: Settings, image_id: uuid.UUID) -> None:
    """Refait une image à la demande du parent (déjà « en préparation »)."""
    engine = image_engine_for(settings)
    if engine is None:
        return
    try:
        await illustration.illustrate_one(database, llm, engine, settings, image_id)
    except Exception:
        logger.exception("Image %s non refaite", image_id)
        await _unstick(database, LessonImage.id == image_id)


async def _unstick(database: Database, which: ColumnElement[bool]) -> None:
    async with database.sessionmaker() as session:
        await session.execute(
            update(LessonImage)
            .where(which, LessonImage.status == "generating")
            .values(status="failed", error="erreur inattendue")
        )
        await session.commit()


IN_PROGRESS = ("uploaded", "reading", "analyzing", "generating")


async def recover_interrupted_lessons(
    database: Database, older_than: timedelta = timedelta(minutes=10)
) -> int:
    """Au démarrage : une analyse interrompue (redémarrage du serveur) ne reste pas « en cours ».

    La leçon passe en échec `ai_error` ; elle se relance sans nouvelle photo si le texte
    avait déjà été lu.
    """
    async with database.sessionmaker() as session:
        result = await session.execute(
            update(Lesson)
            .where(Lesson.status.in_(IN_PROGRESS), Lesson.updated_at < datetime.now(UTC) - older_than)
            .values(status="failed", failure_reason="ai_error")
        )
        await session.commit()
    count: int = result.rowcount  # type: ignore[attr-defined]
    if count:
        logger.warning("%d analyse(s) interrompue(s) marquée(s) en échec", count)
    return count
