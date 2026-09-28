"""Analyse d'une leçon en arrière-plan : le statut avance en base à chaque étape (écran 3)."""

import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.ai.ports import LLMProvider, OcrProvider, PageImage
from app.config import Settings
from app.db.base import Database
from app.db.models import Lesson
from app.domain.activities.registry import ActivityRegistry
from app.services import reading_check, sourced_help
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

    check = None
    if pages:  # une photo : ses dates peuvent être comparées à des sources (étape 24c)
        async with database.sessionmaker() as session:
            if await sourced_help.web_sources_allowed(session, settings, lesson_id):
                check = reading_check.for_settings(settings)
    pipeline = LessonPipeline(
        ocr,
        llm,
        registry,
        max_chars=settings.max_lesson_chars,
        on_status=on_status,
        on_call=lambda stage, model: LIVE.track(lesson_id, stage, model),
        reading_check=check,
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
