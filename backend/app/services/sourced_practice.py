"""Exercices tirés des sites de confiance (étape 29) : préparés après l'analyse, ajoutés au
matériel des notions les plus importantes.

Comme l'aide sourcée (étape 24b) : seulement si le parent l'a permis (`families.web_sources`) et
si le serveur a un moteur de recherche ; en arrière-plan, la leçon est déjà prête. Ludifun
cherche, l'IA propose des questions à partir des extraits, le code ne garde que celles dont la
citation est vérifiée et contient la réponse (`app.domain.sourced_practice`), puis retire celles
que la leçon a déjà (`app.domain.duplicates`). Un échec ne touche jamais la leçon.
"""

import logging
import time
import uuid

from app.ai.ports import AIError, LLMProvider, Prompt
from app.ai.schemas import PracticeOutput
from app.config import Settings
from app.db import models as db
from app.db.base import Database
from app.domain.duplicates import deduplicate
from app.domain.knowledge import KnowledgeItem, KnowledgeMaterial
from app.domain.sourced_practice import NOTIONS, ProposedQuestion, check_practice
from app.domain.sources import Excerpt
from app.services.lesson_store import load_units
from app.services.library import Library
from app.services.sourced_help import web_sources_allowed
from app.services.web_sources import SearchUnavailable, WebSources

logger = logging.getLogger("ludifun.sources")


def practice_input(item: KnowledgeItem, grade: str, excerpts: list[Excerpt]) -> str:
    def safe(text: str) -> str:  # une page ne peut pas fermer sa balise
        return text.replace("<", "‹").replace(">", "›")

    blocks = "\n\n".join(
        f'<source numero="{e.number}" site="{e.site}">\n{safe(e.text)}\n</source>' for e in excerpts
    )
    return (
        f"Classe de l'élève : {grade}\n\n<notion>\n{safe(item.label)} : {safe(item.statement)}\n</notion>"
        f"\n\n{blocks}"
    )


async def prepare(
    database: Database,
    llm: LLMProvider,
    settings: Settings,
    lesson_id: uuid.UUID,
    web: WebSources | None = None,
) -> int:
    """Ajoute des questions tirées des sites de confiance ; renvoie le nombre de questions gardées."""
    async with database.sessionmaker() as session:
        if not await web_sources_allowed(session, settings, lesson_id):
            return 0
        lesson = await session.get(db.Lesson, lesson_id)
        if lesson is None or lesson.status != "ready":
            return 0
        units = await load_units(session, lesson)
        chosen = sorted(units.units, key=lambda u: -u.item.importance)[:NOTIONS]
        if not chosen:
            return 0
        assert settings.web_search_url is not None
        web = web or WebSources(settings.web_search_url, settings.web_sites, library=Library(database))
        prompt = Prompt.load("practice")
        grade = lesson.grade or "CM1"
        # Le matériel à jour de chaque notion : une question ajoutée à l'une compte pour les suivantes.
        materials: dict[str, KnowledgeMaterial] = {u.id: u.material for u in units.units}
        added = 0
        for unit in chosen:
            question = f"{unit.item.label} ({lesson.title})" if lesson.title else unit.item.label
            try:
                excerpts = await web.excerpts(question)
            except SearchUnavailable as exc:
                logger.warning("Exercices des sources impossibles : %s", exc)
                break
            if not excerpts:
                continue
            started = time.perf_counter()
            try:
                result = await llm.structured(
                    prompt=prompt, input=practice_input(unit.item, grade, excerpts), schema=PracticeOutput
                )
            except AIError as exc:
                session.add(_run(lesson_id, llm, prompt, started, exc.status, [str(exc)]))
                await session.commit()
                continue
            checked = check_practice(
                unit.item,
                [
                    ProposedQuestion(q.stem, q.answer, q.distractors, q.difficulty, q.source, q.quote)
                    for q in result.output.questions
                ],
                excerpts,
            )
            candidate = materials[unit.id].model_copy(
                update={"questions": [*materials[unit.id].questions, *checked.questions]}
            )
            others = [(k, m) for k, m in materials.items() if k != unit.id]
            kept = deduplicate([(unit.id, candidate)], lambda _, __: True, already=others)[unit.id]
            new = len(kept.material.questions) - len(materials[unit.id].questions)
            warnings = [f"{r.element} : {r.reason}" for r in checked.rejected + kept.removed]
            usage = result.usage
            session.add(
                db.AiRun(
                    lesson_id=lesson_id,
                    stage="practice",
                    provider=usage.provider,
                    model=usage.model,
                    prompt_version=prompt.version,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    latency_ms=usage.latency_ms,
                    status="ok" if checked.questions or not result.output.questions else "invalid_output",
                    warnings=warnings[:10],
                )
            )
            if new > 0:
                row = await session.get(db.KnowledgeMaterial, units.key_to_id[unit.id])
                if row is not None:
                    row.material = kept.material.model_dump(mode="json")
                    materials[unit.id] = kept.material
                    added += new
            await session.commit()
        if added:
            logger.info("Leçon %s : %d question(s) tirée(s) des sites de confiance", lesson_id, added)
        return added


def _run(
    lesson_id: uuid.UUID, llm: LLMProvider, prompt: Prompt, started: float, status: str, warnings: list[str]
) -> db.AiRun:
    return db.AiRun(
        lesson_id=lesson_id,
        stage="practice",
        provider=llm.name,
        model=llm.model_for("practice"),
        prompt_version=prompt.version,
        latency_ms=round((time.perf_counter() - started) * 1000),
        status=status,
        warnings=warnings[:10],
    )
