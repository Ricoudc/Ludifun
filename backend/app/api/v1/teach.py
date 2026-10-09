"""« Enseigne-moi » (CDC §83) : l'enfant explique une notion de sa leçon à Ludi, l'élève joué par
l'IA, qui pose une ou deux questions de relance (`app.domain.teach`).

Le code choisit la notion (si l'enfant ne l'a pas choisie), décide du nombre de tours, des
points clés retenus et du niveau « expliquer » ; la raison de la décision est enregistrée.
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app import clock
from app.api.deps import AppSettings, ChildAi, ChildInScope, CurrentParent, DbSession, rate_limit
from app.api.errors import ApiError
from app.api.v1.children import own_child
from app.api.v1.lessons import ensure_ai_budget, lesson_of_child
from app.db import models as db
from app.domain.decisions import describe
from app.domain.rules import RULES
from app.domain.teach import (
    ANSWER_MAX_LENGTH,
    Turn,
    choose_notion,
    key_points,
    opening,
    outcome,
    summary,
)
from app.domain.text import display_text
from app.domain.understanding import CognitiveLevel
from app.services import ai_budget
from app.services.lesson_store import load_masteries, load_units
from app.services.teach import ludi_reply

router = APIRouter(tags=["enseigne-moi"])


class TeachStartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    knowledge_id: uuid.UUID | None = Field(
        None, description="La notion à expliquer ; sinon choisie par le moteur."
    )


class TeachAnswerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=ANSWER_MAX_LENGTH, description="L'explication de l'enfant.")


class TeachMessageOut(BaseModel):
    speaker: Literal["ludi", "child"]
    text: str


class TeachOut(BaseModel):
    id: uuid.UUID
    lesson_id: uuid.UUID
    knowledge_id: uuid.UUID
    label: str = Field(description="La notion expliquée.")
    status: Literal["open", "finished"]
    messages: list[TeachMessageOut] = Field(
        description="La conversation ; la dernière question de Ludi attend."
    )
    total: int = Field(description="Points clés attendus.")
    covered: int | None = Field(description="Points clés expliqués : à la fin.")
    validated: bool | None = Field(description="Niveau « expliquer » validé : à la fin.")
    summary: str | None = Field(description="Le bilan de Ludi : à la fin.")
    created_at: datetime


class TeachTurnOut(BaseModel):
    question: str
    answer: str


class TeachSummaryOut(BaseModel):
    """Pour le parent : la notion, ce que l'enfant a expliqué, le bilan et sa raison."""

    id: uuid.UUID
    created_at: datetime
    lesson_id: uuid.UUID
    lesson_title: str | None
    label: str
    status: Literal["open", "finished"]
    total: int
    covered: int | None
    validated: bool | None
    decision: str | None = Field(description="La règle appliquée, en une phrase.")
    turns: list[TeachTurnOut]


class TeachListOut(BaseModel):
    teach: list[TeachSummaryOut]
    next_before: datetime | None


def _turns(row: db.TeachSession) -> list[Turn]:
    return [Turn.from_json(t) for t in row.turns]


def teach_out(row: db.TeachSession, label: str) -> TeachOut:
    messages: list[TeachMessageOut] = []
    for turn in _turns(row):
        messages.append(TeachMessageOut(speaker="ludi", text=display_text(turn.question)))
        messages.append(TeachMessageOut(speaker="child", text=turn.answer))
        if turn.reaction:
            messages.append(TeachMessageOut(speaker="ludi", text=display_text(turn.reaction)))
    if row.status == "open" and row.question:
        messages.append(TeachMessageOut(speaker="ludi", text=display_text(row.question)))
    finished = row.status == "finished"
    bilan = summary(row.covered, len(row.key_points)) if finished and row.covered is not None else None
    return TeachOut(
        id=row.id,
        lesson_id=row.lesson_id,
        knowledge_id=row.knowledge_id,
        label=label,
        status="finished" if finished else "open",
        messages=messages,
        total=len(row.key_points),
        covered=row.covered,
        validated=row.validated,
        summary=display_text(bilan) if bilan else None,
        created_at=row.created_at,
    )


async def _label(dbs: DbSession, knowledge_id: uuid.UUID) -> str:
    return await dbs.scalar(select(db.KnowledgeItem.label).where(db.KnowledgeItem.id == knowledge_id)) or ""


@router.post("/lessons/{lesson_id}/teach", status_code=status.HTTP_201_CREATED)
async def start_teaching(
    lesson_id: uuid.UUID,
    body: TeachStartIn,
    request: Request,
    child: ChildInScope,
    dbs: DbSession,
    settings: AppSettings,
) -> TeachOut:
    """Ludi demande à l'enfant de lui expliquer une notion de la leçon (sans appel à l'IA)."""
    lesson = await lesson_of_child(dbs, child, lesson_id)
    if lesson.status != "ready":
        raise ApiError(409, "lesson_not_ready", "Cette leçon n'est pas encore prête.")
    await ensure_ai_budget(dbs, settings)
    rate_limit(request, f"teach:{child.id}", limit=settings.lessons_per_day, window_s=86400)
    units = await load_units(dbs, lesson)
    if body.knowledge_id is not None:
        key = units.id_to_key.get(body.knowledge_id)
        unit = next((u for u in units.units if u.id == key), None)
        if unit is None:
            raise ApiError(404, "knowledge_not_found", "Notion introuvable dans cette leçon.")
    else:
        unit = choose_notion(units.units, await load_masteries(dbs, child.id, units))
        if unit is None:
            raise ApiError(409, "no_notion", "Cette leçon n'a pas de notion à expliquer.")
    row = db.TeachSession(
        child_id=child.id,
        lesson_id=lesson.id,
        knowledge_id=units.key_to_id[unit.id],
        status="open",
        key_points=key_points(unit.item, unit.material),
        turns=[],
        question=opening(unit.item.label),
        created_at=clock.now(),
    )
    dbs.add(row)
    await dbs.commit()
    return teach_out(row, unit.item.label)


async def _session_of_child(dbs: DbSession, child: db.Child, teach_id: uuid.UUID) -> db.TeachSession:
    row = await dbs.scalar(
        select(db.TeachSession)
        .where(db.TeachSession.id == teach_id, db.TeachSession.child_id == child.id)
        .with_for_update()
    )
    if row is None:
        raise ApiError(404, "teach_not_found", "Conversation introuvable.")
    return row


@router.get("/teach/{teach_id}")
async def get_teaching(teach_id: uuid.UUID, child: ChildInScope, dbs: DbSession) -> TeachOut:
    row = await dbs.scalar(
        select(db.TeachSession).where(db.TeachSession.id == teach_id, db.TeachSession.child_id == child.id)
    )
    if row is None:
        raise ApiError(404, "teach_not_found", "Conversation introuvable.")
    return teach_out(row, await _label(dbs, row.knowledge_id))


@router.post("/teach/{teach_id}/answers")
async def explain(
    teach_id: uuid.UUID,
    body: TeachAnswerIn,
    child: ChildInScope,
    dbs: DbSession,
    settings: AppSettings,
    ai: ChildAi,
) -> TeachOut:
    """L'explication de l'enfant ; Ludi réagit et relance, ou fait le bilan au dernier tour."""
    row = await _session_of_child(dbs, child, teach_id)
    if row.status != "open" or row.question is None:
        raise ApiError(409, "teach_finished", "Cette conversation est terminée.")
    text = body.text.strip()
    if not text:
        raise ApiError(422, "empty_answer", "Écris ton explication avant de l'envoyer.")
    item = await dbs.get(db.KnowledgeItem, row.knowledge_id)
    if item is None:
        raise ApiError(404, "teach_not_found", "Conversation introuvable.")
    pages = await dbs.scalars(select(db.LessonPage.ocr_text).where(db.LessonPage.lesson_id == row.lesson_id))
    over_budget = await ai_budget.seconds_until_budget(dbs, settings.ai_daily_budget_usd, clock.now())
    points = list(row.key_points)
    turns = [*_turns(row), Turn(row.question, text)]
    done = await ludi_reply(
        None if over_budget is not None else ai.llm,
        grade=child.grade,
        label=item.label,
        statement=item.statement,
        points=points,
        turns=turns,
        context=[item.label, item.statement, item.source_excerpt, *points, *pages],
    )
    if done.run is not None:
        run = done.run
        dbs.add(
            db.AiRun(
                lesson_id=row.lesson_id,
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
    reply = done.reply
    turns[-1] = Turn(row.question, text, reply.found, reply.reaction)
    row.turns = [t.to_json() for t in turns]
    row.question = reply.question
    if reply.question is None:
        mastery = await dbs.scalar(
            select(db.KnowledgeMastery)
            .where(db.KnowledgeMastery.child_id == child.id, db.KnowledgeMastery.knowledge_id == item.id)
            .with_for_update()
        )
        result = outcome(points, turns, practised=mastery is not None)
        row.status, row.finished_at = "finished", clock.now()
        row.covered, row.validated = len(result.covered), result.validated
        row.decision, row.engine_version = result.decision, RULES.version
        if result.validated and mastery is not None and CognitiveLevel.EXPLAIN not in mastery.levels:
            mastery.levels = sorted({*mastery.levels, int(CognitiveLevel.EXPLAIN)})
    await dbs.commit()
    return teach_out(row, item.label)


@router.get("/children/{child_id}/teach")
async def list_teaching(
    child_id: uuid.UUID,
    parent: CurrentParent,
    dbs: DbSession,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    before: Annotated[
        datetime | None, Query(description="Curseur : `next_before` de la page précédente")
    ] = None,
) -> TeachListOut:
    """Ce que l'enfant a expliqué à Ludi, notion par notion, et le bilan du moteur."""
    child = await own_child(dbs, parent, child_id)
    query = (
        select(db.TeachSession, db.KnowledgeItem.label, db.Lesson.title)
        .join(db.KnowledgeItem, db.KnowledgeItem.id == db.TeachSession.knowledge_id)
        .join(db.Lesson, db.Lesson.id == db.TeachSession.lesson_id)
        .where(db.TeachSession.child_id == child.id)
        .order_by(db.TeachSession.created_at.desc())
        .limit(limit)
    )
    if before is not None:
        query = query.where(db.TeachSession.created_at < before)
    rows = (await dbs.execute(query)).all()
    out = [
        TeachSummaryOut(
            id=row.id,
            created_at=row.created_at,
            lesson_id=row.lesson_id,
            lesson_title=title,
            label=label,
            status="finished" if row.status == "finished" else "open",
            total=len(row.key_points),
            covered=row.covered,
            validated=row.validated,
            decision=describe(row.decision),
            turns=[TeachTurnOut(question=t.question, answer=t.answer) for t in _turns(row)],
        )
        for row, label, title in rows
    ]
    return TeachListOut(teach=out, next_before=rows[-1][0].created_at if len(rows) == limit else None)
