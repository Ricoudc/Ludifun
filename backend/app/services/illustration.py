"""Image d'une leçon (étape 27), préparée en arrière-plan une fois la leçon prête.

Tout s'enchaîne sur la même carte graphique, jamais en même temps :
1. l'IA de texte propose la scène (étape « illustration », journalisée) ;
2. le code la contrôle et construit le prompt (`app.domain.illustration`) ;
3. Ollama est déchargé, le moteur d'images calcule, puis libère la carte ;
4. l'image est enregistrée, en attente de la validation du parent.

Un échec (moteur éteint, scène refusée) ne touche jamais la leçon : elle reste sans image.
"""

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.imagegen.ports import ImageEngine, ImageEngineError, ImageRequest
from app.ai.ports import AIError, LLMProvider, Prompt
from app.ai.providers.ollama import gpu_lock, unload_models
from app.ai.schemas import IllustrationOutput
from app.config import Settings
from app.db import models as db
from app.db.base import Database
from app.domain.illustration import ImageStatus, build_prompt, clean_remark, validate_scene

logger = logging.getLogger("ludifun.images")

EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


def media_dir(settings: Settings) -> Path:
    path = Path(settings.media_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def image_path(settings: Settings, row: db.LessonImage) -> Path | None:
    if not row.file_name:
        return None
    path = media_dir(settings) / row.file_name
    return path if path.is_file() else None


def illustration_input(lesson: db.Lesson, grade: str, notions: list[str], remark: str | None) -> str:
    def safe(text: str) -> str:
        return text.replace("<", "‹").replace(">", "›")

    lines = "\n".join(f"- {safe(n)}" for n in notions)
    parts = [
        f"Classe de l'élève : {grade}",
        "<lecon>\n"
        f"Titre : {safe(lesson.title or '')}\nRésumé : {safe(lesson.summary or '')}\n"
        f"Notions principales :\n{lines}\n</lecon>",
    ]
    if remark:
        parts.append(f"<remarque_parent>\n{remark}\n</remarque_parent>")
    return "\n\n".join(parts)


async def start(session: AsyncSession, lesson_id: uuid.UUID, remark: str | None = None) -> db.LessonImage:
    """Crée (ou remet à zéro) l'image de la leçon, à l'état « en préparation »."""
    row = await session.scalar(select(db.LessonImage).where(db.LessonImage.lesson_id == lesson_id))
    if row is None:
        row = db.LessonImage(lesson_id=lesson_id, status=ImageStatus.GENERATING.value)
        session.add(row)
    else:
        row.status = ImageStatus.GENERATING.value
        row.error = None
    row.remark = clean_remark(remark)
    await session.flush()
    return row


@contextlib.asynccontextmanager
async def graphics_card(engine: ImageEngine, settings: Settings) -> AsyncIterator[None]:
    """La carte graphique pour le moteur d'images seul : les demandes à Ollama attendent, Ollama
    est déchargé avant, le moteur d'images libère la carte après."""
    urls = {u for u in (settings.ollama_base_url, engine.base_url) if u}
    locks = {id(gpu_lock(u)): gpu_lock(u) for u in sorted(urls)}  # même PC : un seul verrou
    async with contextlib.AsyncExitStack() as stack:
        for lock in locks.values():
            await stack.enter_async_context(lock)
        if engine.base_url is not None and settings.ollama_base_url:
            unloaded = await unload_models(settings.ollama_base_url)
            if unloaded:
                logger.info("Images : Ollama déchargé (%s) avant de dessiner", ", ".join(unloaded))
        try:
            yield
        finally:
            await engine.release()


async def illustrate(
    database: Database,
    llm: LLMProvider,
    engine: ImageEngine,
    settings: Settings,
    lesson_id: uuid.UUID,
) -> ImageStatus:
    """Prépare l'image de la leçon (déjà marquée « en préparation ») ; renvoie son statut final."""
    async with database.sessionmaker() as session:
        row = await session.scalar(select(db.LessonImage).where(db.LessonImage.lesson_id == lesson_id))
        lesson = await session.get(db.Lesson, lesson_id)
        if row is None or lesson is None or lesson.status != "ready":
            return ImageStatus.FAILED
        child = await session.get(db.Child, lesson.child_id)
        grade = child.grade if child is not None else (lesson.grade or "CM1")
        notions = list(
            await session.scalars(
                select(db.KnowledgeItem.statement)
                .where(db.KnowledgeItem.lesson_id == lesson_id)
                .order_by(db.KnowledgeItem.importance.desc(), db.KnowledgeItem.position)
                .limit(5)
            )
        )

        async def fail(reason: str) -> ImageStatus:
            row.status, row.error = ImageStatus.FAILED.value, reason[:300]
            await session.commit()
            logger.warning("Image de la leçon %s non faite : %s", lesson_id, reason)
            return ImageStatus.FAILED

        # 1. La scène, proposée par l'IA de texte.
        prompt = Prompt.load("illustration")
        started = time.perf_counter()
        try:
            result = await llm.structured(
                prompt=prompt,
                input=illustration_input(lesson, grade, notions, row.remark),
                schema=IllustrationOutput,
            )
        except AIError as exc:
            session.add(_run(lesson_id, llm, prompt, None, started, exc.status, [str(exc)]))
            return await fail(f"scène non proposée : {exc.status}")
        scene, reason = validate_scene(result.output.scene, result.output.alt)
        session.add(
            _run(
                lesson_id,
                llm,
                prompt,
                result,
                started,
                "ok" if scene else "invalid_output",
                [reason] if reason else [],
            )
        )
        if scene is None:
            return await fail(reason)

        # 2. Le prompt, construit par le code ; 3. l'image, sur une carte graphique libérée.
        image_prompt = build_prompt(scene, grade)
        request = ImageRequest(
            image_prompt.prompt,
            image_prompt.negative,
            image_prompt.width,
            image_prompt.height,
            seed=uuid.uuid4().int % 2**31,
        )
        try:
            async with graphics_card(engine, settings):
                image = await engine.generate(request)
        except ImageEngineError as exc:
            return await fail(str(exc))

        # 4. L'image, enregistrée en attente du parent (l'ancienne, refusée, est effacée).
        extension = EXTENSIONS.get(image.media_type, "png")
        old = image_path(settings, row)
        name = f"{row.id}-{uuid.uuid4().hex[:8]}.{extension}"
        (media_dir(settings) / name).write_bytes(image.data)
        if old is not None:
            old.unlink(missing_ok=True)
        row.file_name, row.media_type = name, image.media_type
        row.alt, row.prompt = scene.alt, image_prompt.prompt
        row.engine, row.model, row.latency_ms = image.engine, image.model, image.latency_ms
        row.status, row.error = ImageStatus.TO_REVIEW.value, None
        await session.commit()
        logger.info(
            "Image de la leçon %s prête en %d s (%s)", lesson_id, image.latency_ms // 1000, image.engine
        )
        return ImageStatus.TO_REVIEW


def _run(
    lesson_id: uuid.UUID,
    llm: LLMProvider,
    prompt: Prompt,
    result: object,
    started: float,
    status: str,
    warnings: list[str],
) -> db.AiRun:
    usage = getattr(result, "usage", None)
    return db.AiRun(
        lesson_id=lesson_id,
        stage="illustration",
        provider=usage.provider if usage else llm.name,
        model=usage.model if usage else llm.model_for("illustration"),
        prompt_version=prompt.version,
        input_tokens=usage.input_tokens if usage else None,
        output_tokens=usage.output_tokens if usage else None,
        latency_ms=usage.latency_ms if usage else round((time.perf_counter() - started) * 1000),
        status=status,
        warnings=warnings[:10],
    )


def _delete_except(folder: Path, kept: set[str]) -> int:
    if not folder.is_dir():
        return 0
    removed = 0
    for path in folder.iterdir():
        if path.is_file() and path.name not in kept:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def forget_files_later(background: BackgroundTasks, database: Database, settings: Settings) -> None:
    """Après une suppression (leçon, enfant, compte) : les images orphelines sont effacées une fois
    la réponse envoyée."""
    background.add_task(remove_orphan_files, database, settings)


async def remove_orphan_files(database: Database, settings: Settings) -> int:
    """Efface les images dont la leçon a été supprimée (suppression d'une leçon, d'un enfant,
    d'un compte, conservation limitée) : la base les a oubliées, le disque aussi."""
    async with database.sessionmaker() as session:
        names = await session.scalars(
            select(db.LessonImage.file_name).where(db.LessonImage.file_name.is_not(None))
        )
        kept = {name for name in names if name}
    return await asyncio.to_thread(_delete_except, Path(settings.media_dir), kept)
