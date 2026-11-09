"""Exercice neuf sur une erreur qui revient (§5.74) : après une séance terminée, en arrière-plan.

Les erreurs récurrentes de l'enfant sur les notions de la leçon sont recalculées
(`errors.recurring_errors`, 60 derniers jours) ; pour celles qui n'ont pas encore leur exercice,
l'IA propose des questions, le code ne garde que celles dont la réponse est prouvée
(`app.domain.targeted_practice`), sans ce que la leçon a déjà (`lesson_store.add_questions`).
Chaque appel est tracé dans `ai_runs` (étape `targeted`). Un échec ne touche jamais la
progression de l'enfant ni la leçon : au pire, pas d'exercice neuf.
"""

import logging
import time
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.ports import AIError, LLMProvider, Prompt
from app.ai.schemas import TargetedOutput
from app.db import models as db
from app.db.base import Database
from app.domain.errors import ErrorOccurrence, ErrorType, recurring_errors
from app.domain.targeted_practice import ERROR_TARGETS, ProposedTarget, Target, check_targets, targets
from app.services.dashboard import RECURRING_WINDOW
from app.services.lesson_store import LessonUnits, add_questions, load_units

logger = logging.getLogger("ludifun.targeted")


def targeted_input(target: Target, grade: str) -> str:
    def safe(text: str) -> str:  # le texte de la leçon ne peut pas fermer sa balise (§142)
        return text.replace("<", "‹").replace(">", "›")

    item = target.unit.item
    known = "\n".join(f"- {safe(q.stem)} → {safe(q.answer)}" for q in target.unit.material.questions[:8])
    return (
        f"Classe de l'élève : {grade}\n\n<notion>\n{safe(item.label)} : {safe(item.statement)}\n</notion>\n\n"
        f"<deja_posees>\n{known or '(aucune)'}\n</deja_posees>\n\n"
        f"<erreur>\n{ERROR_TARGETS[target.error]}\n</erreur>"
    )


async def _recurring(
    session: AsyncSession, child_id: uuid.UUID, units: LessonUnits, now: datetime
) -> list[Target]:
    rows = await session.execute(
        select(
            db.AttemptEvidence.knowledge_id,
            db.AttemptEvidence.error_type,
            db.SessionItem.session_id,
            db.Attempt.created_at,
        )
        .join(db.Attempt, db.Attempt.id == db.AttemptEvidence.attempt_id)
        .join(db.SessionItem, db.SessionItem.id == db.Attempt.session_item_id)
        .join(db.RevisionSession, db.RevisionSession.id == db.SessionItem.session_id)
        .where(
            db.RevisionSession.child_id == child_id,
            db.AttemptEvidence.knowledge_id.in_(list(units.key_to_id.values())),
            db.AttemptEvidence.error_type.is_not(None),
            db.Attempt.created_at >= now - RECURRING_WINDOW,
        )
    )
    keys = units.id_to_key
    found = recurring_errors(
        ErrorOccurrence(keys[knowledge_id], ErrorType(error), str(session_id), at)
        for knowledge_id, error, session_id, at in rows
    )
    return targets(found, units.units)


async def prepare(
    database: Database, llm: LLMProvider, child_id: uuid.UUID, lesson_id: uuid.UUID, now: datetime
) -> int:
    """Ajoute les exercices neufs ; renvoie le nombre de questions gardées."""
    async with database.sessionmaker() as session:
        lesson = await session.get(db.Lesson, lesson_id)
        child = await session.get(db.Child, child_id)
        if lesson is None or child is None or lesson.status != "ready":
            return 0
        units = await load_units(session, lesson)
        chosen = await _recurring(session, child_id, units, now)
        prompt = Prompt.load("targeted")
        added = 0
        for target in chosen:
            started = time.perf_counter()
            try:
                result = await llm.structured(
                    prompt=prompt,
                    input=targeted_input(target, lesson.grade or child.grade),
                    schema=TargetedOutput,
                )
            except AIError as exc:
                session.add(_run(lesson_id, llm, prompt, started, exc.status, [str(exc)]))
                await session.commit()
                continue
            checked = check_targets(
                target,
                [
                    ProposedTarget(q.stem, q.answer, q.distractors, q.difficulty, q.trap, q.why)
                    for q in result.output.questions
                ],
            )
            new, removed = await add_questions(session, lesson_id, target.unit.id, checked.questions)
            usage = result.usage
            session.add(
                db.AiRun(
                    lesson_id=lesson_id,
                    stage="targeted",
                    provider=usage.provider,
                    model=usage.model,
                    prompt_version=prompt.version,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    latency_ms=usage.latency_ms,
                    status="ok" if checked.questions or not result.output.questions else "invalid_output",
                    warnings=[f"{r.element} : {r.reason}" for r in checked.rejected + removed][:10],
                )
            )
            added += new
            await session.commit()
        if added:  # journal technique : ni prénom ni texte de leçon
            logger.info("Leçon %s : %d exercice(s) neuf(s) sur une erreur qui revient", lesson_id, added)
        return added


async def prepare_quietly(
    database: Database, llm: LLMProvider, child_id: uuid.UUID, lesson_id: uuid.UUID, now: datetime
) -> None:
    """Tâche de fond : une panne ne remonte jamais jusqu'à l'enfant."""
    try:
        await prepare(database, llm, child_id, lesson_id, now)
    except Exception:  # tâche de fond : tout est journalisé, rien n'est perdu
        logger.exception("Exercice neuf sur une erreur qui revient : échec (leçon %s)", lesson_id)


def _run(
    lesson_id: uuid.UUID, llm: LLMProvider, prompt: Prompt, started: float, status: str, warnings: list[str]
) -> db.AiRun:
    return db.AiRun(
        lesson_id=lesson_id,
        stage="targeted",
        provider=llm.name,
        model=llm.model_for("targeted"),
        prompt_version=prompt.version,
        latency_ms=round((time.perf_counter() - started) * 1000),
        status=status,
        warnings=warnings[:10],
    )
