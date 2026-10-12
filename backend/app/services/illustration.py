"""Images d'une leçon (étapes 27 et 28), préparées en arrière-plan une fois la leçon prête.

Tout s'enchaîne sur la même carte graphique, jamais en même temps :
1. l'IA de texte dit si une image aide à retenir la leçon et quelles notions concrètes se
   dessinent (étape « illustration », journalisée) ;
2. le code contrôle chaque scène et construit les prompts (`app.domain.illustration`) ;
3. Ollama est déchargé, le moteur d'images dessine tout à la suite, puis libère la carte ;
4. chaque image est enregistrée, en attente de la validation du parent.

Un échec (moteur éteint, scène refusée) ne touche jamais la leçon : elle reste sans image, et
les jeux en images ne sont simplement pas proposés.

Avant tout cela (§5.61), le code dessine ce qui doit être exact : les figures de géométrie d'une
leçon de mathématiques, les schémas légendés et les cartes de la bibliothèque de figures
(`app.domain.diagrams`). Sans IA ni carte graphique, en quelques millisecondes, et même sans
moteur d'images ; ces notions ne sont pas demandées au moteur.
"""

import asyncio
import contextlib
import json
import logging
import random
import time
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
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
from app.domain.diagrams import VERSION as DRAWING_VERSION
from app.domain.diagrams import Drawing, DrawingPlan, Planned, draw_planned, find_shape, plan_drawings
from app.domain.figures import default_library, figure_path
from app.domain.illustration import (
    IllustrationPlan,
    ImageStatus,
    ProposedPicture,
    Scene,
    build_prompt,
    clean_remark,
    plan_illustrations,
)
from app.services.drawing_render import render

logger = logging.getLogger("ludifun.images")
CODE_ENGINE = "ludifun"  # image dessinée par le code (figure exacte, schéma légendé)

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


NOTIONS_SHOWN = 12  # notions données à l'IA (les plus importantes)
COVER = "lecon"  # cible : l'image de la leçon


@dataclass(frozen=True)
class Notion:
    ref: str  # N1, N2… : ce que voit l'IA
    id: uuid.UUID
    label: str
    statement: str


def illustration_input(
    lesson: db.Lesson,
    grade: str,
    notions: list[Notion],
    remark: str | None,
    target: str | None = None,
    drawn: Sequence[str] = (),
) -> str:
    def safe(text: str) -> str:
        return text.replace("<", "‹").replace(">", "›")

    lines = "\n".join(f"- {n.ref} : {safe(n.label)} — {safe(n.statement)}" for n in notions)
    parts = [
        f"Classe de l'élève : {grade}",
        "<lecon>\n"
        f"Titre : {safe(lesson.title or '')}\nRésumé : {safe(lesson.summary or '')}\n"
        f"Notions :\n{lines}\n</lecon>",
    ]
    if drawn:
        parts.append(f"<deja_dessinees>{', '.join(drawn)}</deja_dessinees>")
    if target:
        parts.append(f"<cible>{target}</cible>")
    if remark:
        parts.append(f"<remarque_parent>\n{remark}\n</remarque_parent>")
    return "\n\n".join(parts)


async def image_of(
    session: AsyncSession, lesson_id: uuid.UUID, knowledge_id: uuid.UUID | None
) -> db.LessonImage | None:
    """L'image de la leçon (`knowledge_id` vide) ou d'une de ses notions."""
    owner = (
        db.LessonImage.knowledge_id.is_(None)
        if knowledge_id is None
        else db.LessonImage.knowledge_id == knowledge_id
    )
    row: db.LessonImage | None = await session.scalar(
        select(db.LessonImage).where(db.LessonImage.lesson_id == lesson_id, owner)
    )
    return row


async def start(
    session: AsyncSession,
    lesson_id: uuid.UUID,
    remark: str | None = None,
    knowledge_id: uuid.UUID | None = None,
) -> db.LessonImage:
    """Crée (ou remet à zéro) une image de la leçon (`knowledge_id` vide) ou d'une notion, à
    l'état « en préparation »."""
    row = await image_of(session, lesson_id, knowledge_id)
    if row is None:
        row = db.LessonImage(
            lesson_id=lesson_id, knowledge_id=knowledge_id, status=ImageStatus.GENERATING.value
        )
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


async def _context(
    session: AsyncSession, lesson_id: uuid.UUID, keep: uuid.UUID | None = None
) -> tuple[db.Lesson, str, list[Notion]] | None:
    """La leçon prête, la classe de l'enfant et les notions numérotées (la plus importante
    d'abord ; `keep` y figure toujours)."""
    lesson = await session.get(db.Lesson, lesson_id)
    if lesson is None or lesson.status != "ready":
        return None
    child = await session.get(db.Child, lesson.child_id)
    grade = child.grade if child is not None else (lesson.grade or "CM1")
    items = list(
        await session.scalars(
            select(db.KnowledgeItem)
            .where(db.KnowledgeItem.lesson_id == lesson_id)
            .order_by(db.KnowledgeItem.importance.desc(), db.KnowledgeItem.position)
        )
    )
    shown = items[:NOTIONS_SHOWN] + [i for i in items[NOTIONS_SHOWN:] if i.id == keep]
    notions = [Notion(f"N{n}", i.id, i.label, i.statement) for n, i in enumerate(shown, start=1)]
    return lesson, grade, notions


async def _propose(
    session: AsyncSession,
    llm: LLMProvider,
    lesson: db.Lesson,
    grade: str,
    notions: list[Notion],
    remark: str | None,
    target: str | None,
    drawn: Sequence[str] = (),
) -> IllustrationPlan | str:
    """La proposition de l'IA, contrôlée par le code ; ou la raison de l'échec. Les notions
    `drawn` (dessinées par le code) ne sont pas demandées."""
    prompt = Prompt.load("illustration")
    started = time.perf_counter()
    try:
        result = await llm.structured(
            prompt=prompt,
            input=illustration_input(lesson, grade, notions, remark, target, drawn),
            schema=IllustrationOutput,
        )
    except AIError as exc:
        session.add(_run(lesson.id, llm, prompt, None, started, exc.status, [str(exc)]))
        return f"scène non proposée : {exc.status}"
    out = result.output
    plan = plan_illustrations(
        None if target else out.useful,  # une image demandée par le parent est toujours faite
        out.why,
        out.scene,
        out.alt,
        [ProposedPicture(p.notion, p.scene, p.alt) for p in out.pictures],
        [n.ref for n in notions if n.ref not in drawn] if target in (None, COVER) else [target or ""],
    )
    warnings = ([] if plan.cover or not plan.cover_needed else [plan.cover_issue]) + list(
        plan.refused.values()
    )
    nothing = plan.cover_needed and plan.cover is None and not plan.pictures
    session.add(
        _run(lesson.id, llm, prompt, result, started, "invalid_output" if nothing else "ok", warnings)
    )
    return plan


def drawing_plan(lesson: db.Lesson, notions: Sequence[Notion]) -> DrawingPlan:
    """Ce que le code dessine exactement pour cette leçon (§5.61)."""
    return plan_drawings(
        lesson.subject, lesson.title, [(n.ref, n.label, n.statement) for n in notions], default_library()
    )


def _figure_data(figure_id: str | None) -> dict[str, object] | None:
    path = figure_path(figure_id) if figure_id else None
    return json.loads(path.read_text(encoding="utf-8")) if path is not None else None


async def _save_drawing(
    session: AsyncSession, settings: Settings, row: db.LessonImage, drawing: Drawing
) -> None:
    """Le dessin du code, en PNG, enregistré en attente du parent (comme une image du moteur)."""
    started = time.perf_counter()
    data = await asyncio.to_thread(render, drawing)
    old = image_path(settings, row)
    name = f"{row.id}-{uuid.uuid4().hex[:8]}.png"
    (media_dir(settings) / name).write_bytes(data)
    if old is not None:
        old.unlink(missing_ok=True)
    row.file_name, row.media_type = name, "image/png"
    row.alt, row.prompt = drawing.alt, drawing.key
    row.engine, row.model = CODE_ENGINE, f"schéma v{DRAWING_VERSION}"
    row.latency_ms = round((time.perf_counter() - started) * 1000)
    row.status, row.error = ImageStatus.TO_REVIEW.value, None
    await session.commit()


async def _draw_planned(
    session: AsyncSession,
    settings: Settings,
    row: db.LessonImage,
    planned: Planned,
    title: str,
    variant: int = 0,
) -> None:
    figure = await asyncio.to_thread(_figure_data, planned.figure)
    drawing = draw_planned(planned, figure, title, row.knowledge_id is None, variant)
    await _save_drawing(session, settings, row, drawing)


async def can_draw(
    session: AsyncSession,
    lesson_id: uuid.UUID,
    knowledge_id: uuid.UUID | None = None,
    remark: str | None = None,
) -> bool:
    """Le code sait-il dessiner cette image (celle de la leçon, ou d'une notion) sans moteur
    d'images ? Oui pour une figure de géométrie ou un schéma, ou si le parent en nomme une."""
    if remark and find_shape(remark) is not None:
        return True
    context = await _context(session, lesson_id, keep=knowledge_id)
    if context is None:
        return False
    lesson, _, notions = context
    plan = drawing_plan(lesson, notions)
    if knowledge_id is None:
        return plan.cover is not None
    ref = next((n.ref for n in notions if n.id == knowledge_id), None)
    return ref in plan.pictures


async def _draw(
    session: AsyncSession,
    engine: ImageEngine,
    settings: Settings,
    grade: str,
    jobs: list[tuple[db.LessonImage, Scene]],
) -> None:
    """Dessine les images l'une après l'autre, la carte graphique prise une seule fois ; chacune
    est enregistrée dès qu'elle est prête (le parent la voit arriver)."""
    if not jobs:
        return
    async with graphics_card(engine, settings):
        for row, scene in jobs:
            image_prompt = build_prompt(scene, grade, single_subject=row.knowledge_id is not None)
            request = ImageRequest(
                image_prompt.prompt,
                image_prompt.negative,
                image_prompt.width,
                image_prompt.height,
                seed=uuid.uuid4().int % 2**31,
            )
            try:
                image = await engine.generate(request)
            except ImageEngineError as exc:
                row.status, row.error = ImageStatus.FAILED.value, str(exc)[:300]
                await session.commit()
                logger.warning("Image %s non faite : %s", row.id, exc)
                continue
            # L'image, enregistrée en attente du parent (l'ancienne, refusée, est effacée).
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
            logger.info("Image %s prête en %d s (%s)", row.id, image.latency_ms // 1000, image.engine)


def _fail(row: db.LessonImage, reason: str, status: ImageStatus = ImageStatus.FAILED) -> None:
    row.status, row.error = status.value, reason[:300]


async def illustrate_lesson(
    database: Database,
    llm: LLMProvider | None,
    engine: ImageEngine | None,
    settings: Settings,
    lesson_id: uuid.UUID,
) -> None:
    """Après l'analyse (image de la leçon déjà « en préparation ») : le code dessine d'abord ce
    qui doit être exact (§5.61) ; puis, s'il y a un moteur d'images, l'IA dit si une image aide
    et quelles autres notions se dessinent ; le code contrôle, puis tout est dessiné à la suite."""
    async with database.sessionmaker() as session:
        cover = await image_of(session, lesson_id, None)
        context = await _context(session, lesson_id)
        if cover is None or context is None:
            return
        lesson, grade, notions = context
        title = lesson.title or "À retenir"
        drawing = drawing_plan(lesson, notions)
        by_ref = {n.ref: n for n in notions}
        if drawing.cover is not None:
            await _draw_planned(session, settings, cover, drawing.cover, title)
        for ref, planned in drawing.pictures.items():
            row = await start(session, lesson_id, None, by_ref[ref].id)
            await _draw_planned(session, settings, row, planned, title)
        drawn = list(drawing.pictures)
        if engine is None or llm is None:
            if drawing.cover is None:  # rien d'autre ne se dessine sans moteur d'images
                await session.delete(cover)
                await session.commit()
            return
        if drawing.cover is not None and len(drawn) == len(notions):
            return  # tout est déjà dessiné, exactement
        plan = await _propose(session, llm, lesson, grade, notions, cover.remark, None, drawn)
        if isinstance(plan, str):
            if drawing.cover is None:
                _fail(cover, plan)
            await session.commit()
            logger.warning("Images de la leçon %s non faites : %s", lesson_id, plan)
            return
        jobs: list[tuple[db.LessonImage, Scene]] = []
        if drawing.cover is not None:
            pass  # l'image de la leçon est la fiche mémo dessinée par le code
        elif plan.cover is not None:
            jobs.append((cover, plan.cover))
        elif plan.cover_needed:
            _fail(cover, plan.cover_issue)
        else:
            _fail(cover, plan.cover_issue, ImageStatus.NOT_NEEDED)
            logger.info("Leçon %s : image jugée pas utile", lesson_id)  # sans la raison (texte)
        for ref, scene in plan.pictures.items():
            if ref in drawn:
                continue
            row = await start(session, lesson_id, None, by_ref[ref].id)
            jobs.append((row, scene))
        await session.commit()
        await _draw(session, engine, settings, grade, jobs)


async def illustrate_one(
    database: Database,
    llm: LLMProvider | None,
    engine: ImageEngine | None,
    settings: Settings,
    image_id: uuid.UUID,
) -> ImageStatus:
    """Refait une image (déjà « en préparation ») à la demande du parent, avec sa remarque.
    Une figure nommée par le parent (« un carré ») est dessinée exactement par le code ; une
    figure ou un schéma du code est redessiné par le code, sauf si le parent demande autre chose
    avec un moteur d'images."""
    async with database.sessionmaker() as session:
        row = await session.get(db.LessonImage, image_id)
        if row is None:
            return ImageStatus.FAILED
        context = await _context(session, row.lesson_id, keep=row.knowledge_id)
        if context is None:
            _fail(row, "leçon introuvable")
            await session.commit()
            return ImageStatus.FAILED
        lesson, grade, notions = context
        ref = next((n.ref for n in notions if n.id == row.knowledge_id), None)
        named = find_shape(row.remark) if row.remark else None
        drawing = drawing_plan(lesson, notions)
        planned = (
            Planned(shapes=(named,))
            if named is not None
            else drawing.cover
            if row.knowledge_id is None
            else drawing.pictures.get(ref or "")
        )
        if planned is not None and (named is not None or not row.remark or engine is None or llm is None):
            variant = random.randrange(1, 1000)  # une autre orientation de la figure
            await _draw_planned(session, settings, row, planned, lesson.title or "À retenir", variant)
            return ImageStatus(row.status)
        if engine is None or llm is None:
            _fail(row, "le serveur n'a pas de moteur d'images")
            await session.commit()
            return ImageStatus.FAILED
        target = COVER if row.knowledge_id is None else ref
        plan = await _propose(session, llm, lesson, grade, notions, row.remark, target)
        scene: Scene | None = None
        if isinstance(plan, str):
            _fail(row, plan)
        elif row.knowledge_id is None:
            scene = plan.cover
            if scene is None:
                _fail(row, plan.cover_issue)
        else:
            scene = plan.pictures.get(ref or "")
            if scene is None:
                _fail(row, plan.refused.get(ref or "") or "aucune scène proposée")
        await session.commit()
        if scene is not None:
            await _draw(session, engine, settings, grade, [(row, scene)])
        return ImageStatus(row.status)


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


# Une image vient d'être écrite mais pas encore enregistrée en base (fichier `<id de l'image>-…`,
# ligne encore là) : elle n'est pas orpheline. Celle d'une leçon supprimée l'est tout de suite.
ORPHAN_MIN_AGE_S = 600


def _delete_except(folder: Path, kept: set[str], rows: set[str], min_age_s: float = ORPHAN_MIN_AGE_S) -> int:
    if not folder.is_dir():
        return 0
    removed = 0
    limit = time.time() - min_age_s
    for path in folder.iterdir():
        if not path.is_file() or path.name in kept:
            continue
        in_progress = path.name.split("-", 5)[:5]
        if "-".join(in_progress) in rows and path.stat().st_mtime >= limit:
            continue
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
        rows = (await session.execute(select(db.LessonImage.id, db.LessonImage.file_name))).all()
    kept = {name for _, name in rows if name}
    ids = {str(image_id) for image_id, _ in rows}
    return await asyncio.to_thread(_delete_except, Path(settings.media_dir), kept, ids)
