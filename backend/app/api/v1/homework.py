"""Mode devoirs (CDC §29, §127) : l'enfant est guidé pas à pas sur SON exercice.

L'enfant envoie une photo ou le texte de l'énoncé ; le guidage est préparé en arrière-plan. Il
voit les étapes une par une, essaie sa réponse, et la correction guidée n'arrive qu'après
plusieurs essais (`app.domain.homework`). La réponse attendue n'est jamais envoyée avant.
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, File, Query, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app import clock
from app.ai.images import detect_media_type, is_heic
from app.ai.ports import PageImage
from app.api.deps import (
    AppSettings,
    ChildAi,
    ChildInScope,
    CurrentParent,
    DbSession,
    get_database,
    rate_limit,
)
from app.api.errors import ApiError
from app.api.v1.children import own_child
from app.api.v1.lessons import ensure_ai_budget
from app.db.models import Homework
from app.domain.homework import (
    STATEMENT_MAX_LENGTH,
    AnswerKind,
    AttemptRecord,
    HomeworkPlan,
    judge,
    solution_available,
)
from app.domain.text import display_text
from app.services import homework as homework_service

router = APIRouter(tags=["devoirs"])

FAILURES = {
    homework_service.UNREADABLE: "La photo est difficile à lire : reprends-la à plat, avec de la lumière.",
    homework_service.NOT_EXERCISE: "Je n'ai pas trouvé comment t'aider sur cet exercice sans te donner la "
    "réponse : demande à un adulte.",
    homework_service.AI_ERROR: "Petit souci pour préparer l'aide : réessaie dans un moment.",
}
MIN_STATEMENT = 10
MAX_ATTEMPT_LENGTH = 300


class HomeworkTextIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(
        max_length=STATEMENT_MAX_LENGTH, description="L'énoncé de l'exercice, recopié ou collé."
    )


class AttemptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=MAX_ATTEMPT_LENGTH, description="La réponse de l'enfant.")


class HomeworkStepOut(BaseModel):
    kind: str = Field(description="task, hint, question, reminder ou method.")
    title: str
    text: str


class HomeworkAttemptOut(BaseModel):
    text: str
    correct: bool | None = Field(description="null pour une réponse rédigée (l'enfant compare).")


class HomeworkOut(BaseModel):
    id: uuid.UUID
    status: Literal["preparing", "ready", "solved", "guided", "failed"]
    statement: str | None
    answer_kind: Literal["number", "short", "open"] | None
    steps: list[HomeworkStepOut] = Field(description="Les étapes déjà montrées, dans l'ordre.")
    steps_left: int = Field(description="Étapes encore cachées.")
    attempts: list[HomeworkAttemptOut]
    solution_available: bool = Field(description="La correction guidée peut être demandée.")
    solution: list[str] | None = Field(description="Correction guidée : après réussite ou demande.")
    answer: str | None = Field(description="La réponse attendue : après réussite ou correction guidée.")
    check: str | None = Field(description="Comment vérifier son résultat : après une réussite.")
    failure_message: str | None
    created_at: datetime


class HomeworkSummaryOut(BaseModel):
    """Pour le parent : l'exercice, l'aide utilisée, la suite."""

    id: uuid.UUID
    created_at: datetime
    status: Literal["preparing", "ready", "solved", "guided", "failed"]
    statement: str | None
    steps_used: int = Field(description="Étapes demandées après « Qu'est-ce qu'on cherche ? ».")
    steps_total: int
    attempts: int
    solved_alone: bool = Field(description="Réussi sans aucune étape en plus.")


class HomeworkListOut(BaseModel):
    homework: list[HomeworkSummaryOut]
    next_before: datetime | None


def _attempts(row: Homework) -> list[AttemptRecord]:
    return [AttemptRecord(a["text"], a["correct"]) for a in row.attempts]


def homework_out(row: Homework) -> HomeworkOut:
    plan = HomeworkPlan.from_json(row.plan) if row.plan else None
    attempts = _attempts(row)
    finished = row.status in ("solved", "guided")
    available = plan is not None and not finished and solution_available(plan, row.steps_shown, attempts)
    shown = plan.steps[: row.steps_shown] if plan else ()
    return HomeworkOut(
        id=row.id,
        status=row.status,
        statement=row.statement,
        answer_kind=plan.answer_kind.value if plan else None,
        steps=[HomeworkStepOut(kind=s.kind.value, title=s.title, text=display_text(s.text)) for s in shown],
        steps_left=len(plan.steps) - row.steps_shown if plan else 0,
        attempts=[HomeworkAttemptOut(text=a.text, correct=a.correct) for a in attempts],
        solution_available=available,
        solution=display_text(list(plan.solution)) if plan and finished else None,
        answer=display_text(plan.answer) if plan and finished else None,
        check=display_text(plan.check) if plan and row.status == "solved" else None,
        failure_message=FAILURES.get(row.failure_reason or "") if row.status == "failed" else None,
        created_at=row.created_at,
    )


async def homework_of_child(db: DbSession, child_id: uuid.UUID, homework_id: uuid.UUID) -> Homework:
    row = await db.scalar(
        select(Homework).where(Homework.id == homework_id, Homework.child_id == child_id).with_for_update()
    )
    if row is None:
        raise ApiError(404, "homework_not_found", "Exercice introuvable.")
    return row


async def _start(
    request: Request, db: DbSession, settings: AppSettings, child_id: uuid.UUID, source: str
) -> Homework:
    await ensure_ai_budget(db, settings)
    rate_limit(request, f"homework:{child_id}", limit=settings.lessons_per_day, window_s=86400)
    row = Homework(child_id=child_id, status="preparing", source=source, created_at=clock.now())
    db.add(row)
    return row


@router.post("/homework", status_code=status.HTTP_202_ACCEPTED)
async def create_homework_from_photo(
    request: Request,
    child: ChildInScope,
    db: DbSession,
    settings: AppSettings,
    ai: ChildAi,
    background: BackgroundTasks,
    pages: Annotated[list[UploadFile], File(description="Photo(s) de l'exercice")],
) -> HomeworkOut:
    """La photo est lue puis oubliée (§15) ; le guidage est préparé en arrière-plan."""
    if not 1 <= len(pages) <= 2:
        raise ApiError(422, "invalid_page_count", "Envoie une ou deux photos de l'exercice.")
    images = []
    for upload in pages:
        data = await upload.read(settings.max_image_bytes + 1)
        if len(data) > settings.max_image_bytes:
            raise ApiError(413, "image_too_large", "Cette photo est trop lourde.")
        if is_heic(data):
            raise ApiError(415, "heic_not_supported", "Photo HEIC : l'application doit l'envoyer en JPEG.")
        media_type = detect_media_type(data)
        if media_type is None:
            raise ApiError(
                415, "unsupported_media_type", "Format de photo non pris en charge (JPEG, PNG, WebP)."
            )
        images.append(PageImage(data, media_type))
    row = await _start(request, db, settings, child.id, "photo")
    await db.commit()
    background.add_task(homework_service.prepare, get_database(request), ai.ocr, ai.llm, row.id, images)
    return homework_out(row)


@router.post("/homework/text", status_code=status.HTTP_202_ACCEPTED)
async def create_homework_from_text(
    body: HomeworkTextIn,
    request: Request,
    child: ChildInScope,
    db: DbSession,
    settings: AppSettings,
    ai: ChildAi,
    background: BackgroundTasks,
) -> HomeworkOut:
    text = body.text.strip()
    if len(text) < MIN_STATEMENT:
        raise ApiError(422, "text_too_short", "Recopie tout l'énoncé de l'exercice.")
    row = await _start(request, db, settings, child.id, "text")
    row.statement = text
    await db.commit()
    background.add_task(homework_service.prepare, get_database(request), ai.ocr, ai.llm, row.id)
    return homework_out(row)


@router.get("/homework/{homework_id}")
async def get_homework(homework_id: uuid.UUID, child: ChildInScope, db: DbSession) -> HomeworkOut:
    row = await db.scalar(select(Homework).where(Homework.id == homework_id, Homework.child_id == child.id))
    if row is None:
        raise ApiError(404, "homework_not_found", "Exercice introuvable.")
    return homework_out(row)


def _ready(row: Homework) -> HomeworkPlan:
    if row.status != "ready" or row.plan is None:
        raise ApiError(409, "homework_not_ready", "Cet exercice n'est pas (ou plus) en cours.")
    return HomeworkPlan.from_json(row.plan)


@router.post("/homework/{homework_id}/next-step")
async def next_step(homework_id: uuid.UUID, child: ChildInScope, db: DbSession) -> HomeworkOut:
    """Une étape de plus (« Un indice », « Une question pour avancer »…), dans l'ordre du §127."""
    row = await homework_of_child(db, child.id, homework_id)
    plan = _ready(row)
    if row.steps_shown >= len(plan.steps):
        raise ApiError(409, "no_more_steps", "Tu as vu toutes les étapes : essaie ta réponse !")
    row.steps_shown += 1
    await db.commit()
    return homework_out(row)


@router.post("/homework/{homework_id}/attempts")
async def try_answer(
    homework_id: uuid.UUID, body: AttemptIn, child: ChildInScope, db: DbSession
) -> HomeworkOut:
    """La réponse de l'enfant, vérifiée par le code (sans IA). Juste : l'exercice est réussi."""
    row = await homework_of_child(db, child.id, homework_id)
    plan = _ready(row)
    text = body.text.strip()
    if not text:
        raise ApiError(422, "empty_answer", "Écris ta réponse avant de vérifier.")
    correct = judge(plan, text, row.statement or "")
    row.attempts = [*row.attempts, {"text": text, "correct": correct, "at": clock.now().isoformat()}]
    if correct:
        row.status, row.finished_at = "solved", clock.now()
    await db.commit()
    return homework_out(row)


@router.post("/homework/{homework_id}/solution")
async def show_solution(homework_id: uuid.UUID, child: ChildInScope, db: DbSession) -> HomeworkOut:
    """La correction guidée : seulement après les essais prévus (§127), jamais d'emblée."""
    row = await homework_of_child(db, child.id, homework_id)
    plan = _ready(row)
    if not solution_available(plan, row.steps_shown, _attempts(row)):
        if plan.answer_kind is AnswerKind.OPEN:
            message = "Écris d'abord ta réponse : tu la compareras ensuite avec la correction."
        else:
            message = "Essaie encore, avec les étapes : la correction arrive après plusieurs essais."
        raise ApiError(409, "solution_not_yet", message)
    row.status, row.finished_at = "guided", clock.now()
    await db.commit()
    return homework_out(row)


@router.get("/children/{child_id}/homework")
async def list_homework(
    child_id: uuid.UUID,
    parent: CurrentParent,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    before: Annotated[
        datetime | None, Query(description="Curseur : `next_before` de la page précédente")
    ] = None,
) -> HomeworkListOut:
    """Les exercices de l'enfant en mode devoirs : l'aide utilisée, les essais, la suite."""
    child = await own_child(db, parent, child_id)
    query = (
        select(Homework)
        .where(Homework.child_id == child.id)
        .order_by(Homework.created_at.desc())
        .limit(limit)
    )
    if before is not None:
        query = query.where(Homework.created_at < before)
    rows = list(await db.scalars(query))
    out = []
    for row in rows:
        total = len(row.plan["steps"]) if row.plan else 0
        used = max(0, row.steps_shown - 1)
        out.append(
            HomeworkSummaryOut(
                id=row.id,
                created_at=row.created_at,
                status=row.status,
                statement=row.statement,
                steps_used=used,
                steps_total=max(0, total - 1),
                attempts=len(row.attempts),
                solved_alone=row.status == "solved" and used == 0,
            )
        )
    return HomeworkListOut(homework=out, next_before=rows[-1].created_at if len(rows) == limit else None)
