"""Mode devoirs (§29, §127) : préparer le guidage d'un exercice, en arrière-plan.

La photo n'existe qu'en mémoire, le temps de la lire (§15). L'IA propose les étapes ;
`app.domain.homework.check_plan` les remet dans l'ordre et retire ce qui donnerait la réponse.
Chaque appel à l'IA est journalisé (`ai_runs`, sans lien avec une leçon).
"""

import logging
import time
import uuid
from collections.abc import Sequence

from sqlalchemy import select

from app import clock
from app.ai.ports import AIError, LLMProvider, OcrProvider, PageImage, Prompt
from app.ai.schemas import HomeworkOutput
from app.db import models as db
from app.db.base import Database
from app.domain.homework import STATEMENT_MAX_LENGTH, check_plan, homework_input

logger = logging.getLogger("ludifun.homework")

UNREADABLE = "unreadable"  # photo illisible
NOT_EXERCISE = "not_exercise"  # pas d'étapes possibles sans donner la réponse
AI_ERROR = "ai_error"


def _run(
    stage: str, provider: str, model: str, version: str, started: float, status: str, warnings: list[str]
) -> db.AiRun:
    return db.AiRun(
        lesson_id=None,
        stage=stage,
        provider=provider,
        model=model,
        prompt_version=version,
        latency_ms=round((time.perf_counter() - started) * 1000),
        status=status,
        warnings=warnings[:10],
    )


async def prepare(
    database: Database,
    ocr: OcrProvider,
    llm: LLMProvider,
    homework_id: uuid.UUID,
    pages: Sequence[PageImage] = (),
) -> None:
    async with database.sessionmaker() as session:
        homework = await session.get(db.Homework, homework_id)
        if homework is None:
            return
        grade = await session.scalar(select(db.Child.grade).where(db.Child.id == homework.child_id)) or "CM1"
        statement = homework.statement or ""
        try:
            if pages:
                started = time.perf_counter()
                try:
                    read = await ocr.extract(tuple(pages))
                except AIError as exc:
                    session.add(
                        _run("ocr", ocr.name, ocr.model, ocr.prompt_version, started, exc.status, [str(exc)])
                    )
                    raise
                usage = read.usage
                statement = read.output.text.strip()[:STATEMENT_MAX_LENGTH]
                session.add(
                    db.AiRun(
                        lesson_id=None,
                        stage="ocr",
                        provider=usage.provider,
                        model=usage.model,
                        prompt_version=ocr.prompt_version,
                        input_tokens=usage.input_tokens,
                        output_tokens=usage.output_tokens,
                        latency_ms=usage.latency_ms,
                        status="ok",
                        warnings=read.output.warnings[:10],
                    )
                )
                homework.statement = statement
                if len(statement) < 10 or all(p.quality == "unreadable" for p in read.output.pages):
                    homework.status, homework.failure_reason = "failed", UNREADABLE
                    return
            prompt = Prompt.load("homework")
            started = time.perf_counter()
            try:
                result = await llm.structured(
                    prompt=prompt, input=homework_input(statement, grade), schema=HomeworkOutput
                )
            except AIError as exc:
                session.add(
                    _run(
                        "homework",
                        llm.name,
                        llm.model_for("homework"),
                        prompt.version,
                        started,
                        exc.status,
                        [str(exc)],
                    )
                )
                raise
            plan, rejected = check_plan(result.output.model_dump(), statement)
            usage = result.usage
            session.add(
                db.AiRun(
                    lesson_id=None,
                    stage="homework",
                    provider=usage.provider,
                    model=usage.model,
                    prompt_version=prompt.version,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    latency_ms=usage.latency_ms,
                    status="ok" if plan else "invalid_output",
                    warnings=rejected[:10],
                )
            )
            if plan is None:
                homework.status, homework.failure_reason = "failed", NOT_EXERCISE
                return
            homework.plan = plan.to_json()
            homework.steps_shown = 1  # « Qu'est-ce qu'on cherche ? » d'abord : ne donne rien
            homework.status = "ready"
        except AIError:
            homework.status, homework.failure_reason = "failed", AI_ERROR
        except Exception:  # un bug ne doit pas laisser le devoir « en préparation » pour toujours
            logger.exception("Préparation du devoir %s interrompue", homework_id)
            homework.status, homework.failure_reason = "failed", AI_ERROR
        finally:
            if homework.status == "failed":
                homework.finished_at = clock.now()
            await session.commit()
