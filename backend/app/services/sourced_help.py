"""Aide sourcée (étape 24b) : préparée après l'analyse, montrée par « Je n'ai pas compris ».

Quand la leçon ne donne pas d'exemple pour une notion, Ludifun cherche sur des sites éducatifs
autorisés, l'IA explique autrement en citant, et le code vérifie les citations (§116). Préparé en
arrière-plan, une fois la leçon prête : l'enfant n'attend jamais la recherche. Seulement si le
parent l'a permis (`families.web_sources`) et si le serveur a un moteur de recherche.
"""

import logging
import uuid
from typing import Any

from sqlalchemy import select

from app.ai.ports import LLMProvider
from app.config import Settings
from app.db import models as db
from app.db.base import Database
from app.domain.knowledge import KnowledgeUnit
from app.domain.sources import SourcedAnswer
from app.services.lesson_store import LessonUnits, load_units
from app.services.library import Library
from app.services.sourced_answer import SourcedAnswerer
from app.services.web_sources import SearchUnavailable, WebSources

logger = logging.getLogger("ludifun.sources")

MAX_NOTIONS = 3  # notions les plus importantes sans exemple, par leçon


def help_json(answer: SourcedAnswer) -> dict[str, Any]:
    return {
        "text": answer.text,
        "sources": [{"site": e.site, "url": e.url, "title": e.title} for e in answer.sources],
        "quotes": [{"source": q.source, "text": q.text} for q in answer.quotes],
        "origin": answer.origin,
    }


async def web_sources_allowed(session: Any, settings: Settings, lesson_id: uuid.UUID) -> bool:
    """Le serveur a un moteur de recherche et le parent de l'enfant l'a permis."""
    if not settings.web_search_url:
        return False
    allowed = await session.scalar(
        select(db.Family.web_sources)
        .join(db.Child, db.Child.family_id == db.Family.id)
        .join(db.Lesson, db.Lesson.child_id == db.Child.id)
        .where(db.Lesson.id == lesson_id)
    )
    return bool(allowed)


async def prepare(
    database: Database,
    llm: LLMProvider,
    settings: Settings,
    lesson_id: uuid.UUID,
    web: WebSources | None = None,
) -> int:
    """Prépare l'aide sourcée des notions sans exemple ; renvoie le nombre de notions aidées.
    Un échec (moteur injoignable, IA indisponible, citation fausse) ne touche pas la leçon."""
    async with database.sessionmaker() as session:
        if not await web_sources_allowed(session, settings, lesson_id):
            return 0
        lesson = await session.get(db.Lesson, lesson_id)
        if lesson is None or lesson.status != "ready":
            return 0
        units = await load_units(session, lesson)
        without_example = sorted(
            (u for u in units.units if u.material.help is None or u.material.help.example is None),
            key=lambda u: -u.item.importance,
        )[:MAX_NOTIONS]
        if not without_example:
            return 0
        assert settings.web_search_url is not None
        own = web is None
        web = web or WebSources(settings.web_search_url, settings.web_sites, library=Library(database))
        try:
            return await _help(session, web, llm, lesson, units, without_example)
        finally:
            if own:
                await web.aclose()


async def _help(
    session: Any,
    web: WebSources,
    llm: LLMProvider,
    lesson: db.Lesson,
    units: LessonUnits,
    without_example: list[KnowledgeUnit],
) -> int:
    lesson_id = lesson.id
    answerer = SourcedAnswerer(llm)
    grade = lesson.grade or "CM1"
    helped = 0
    for unit in without_example:
        question = f"{unit.item.label} ({lesson.title})" if lesson.title else unit.item.label
        try:
            excerpts = await web.excerpts(question)
        except SearchUnavailable as exc:
            logger.warning("Aide sourcée impossible : %s", exc)
            break
        if not excerpts:
            continue
        done = await answerer.answer(
            f"Explique simplement « {unit.item.label} » : {unit.item.statement}", grade, excerpts
        )
        run = done.run
        session.add(
            db.AiRun(
                lesson_id=lesson_id,
                stage=run.stage,
                provider=run.provider,
                model=run.model,
                prompt_version=run.prompt_version,
                input_tokens=run.input_tokens,
                output_tokens=run.output_tokens,
                latency_ms=run.latency_ms,
                status=run.status,
                warnings=run.warnings[:10],
            )
        )
        if done.answer is not None:
            row = await session.get(db.KnowledgeItem, units.key_to_id[unit.id])
            if row is not None:
                row.external_help = help_json(done.answer)
                helped += 1
        await session.commit()
    return helped
