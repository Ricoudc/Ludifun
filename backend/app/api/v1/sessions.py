"""Séances de révision (écrans 4 à 7)."""

import uuid
from zoneinfo import ZoneInfo

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import clock
from app.api.deps import Ai, AppSettings, ChildInScope, DbSession, Registry
from app.api.errors import ApiError
from app.api.v1.lessons import lesson_of_child
from app.api.v1.schemas_learning import (
    AttemptIn,
    AttemptOut,
    AttemptSummary,
    HelpOut,
    KnowledgeResultOut,
    ReplayOut,
    ReportOut,
    SessionCreate,
    SessionItemOut,
    SessionOut,
)
from app.db.models import Attempt, Child, RevisionSession, SessionItem
from app.domain.activities.base import ActivityCode, InvalidResponse
from app.domain.composer import Block, NothingToReview
from app.domain.scoring import KnowledgeStatus
from app.services import ai_budget, goals, learning
from app.services.answer_evaluation import AnswerEvaluator

router = APIRouter(tags=["séances"])

MULTI_KNOWLEDGE = {ActivityCode.MATCH, ActivityCode.SPEED_CHALLENGE}
SESSION_CLOSED = ApiError(409, "session_closed", "Cette séance est terminée.")
NOTHING_TO_REVIEW = ApiError(409, "nothing_to_review", "🎉 Tout est à jour ! Rien à réviser pour l'instant.")


def attempt_summary(attempt: Attempt | None) -> AttemptSummary | None:
    if attempt is None:
        return None
    if attempt.response == {"skipped": True}:
        return AttemptSummary(result="skipped", score=0)
    score = float(attempt.score)
    return AttemptSummary(
        result="correct" if score >= 1 else "partial" if score >= 0.5 else "incorrect", score=score
    )


def item_out(item: SessionItem, attempt: Attempt | None = None) -> SessionItemOut:
    return SessionItemOut(
        help_available=item.activity_type not in MULTI_KNOWLEDGE,
        help_level=item.help_level,
        id=item.id,
        position=item.position,
        block=item.block,
        type=item.activity_type,
        difficulty=item.difficulty,
        knowledge_ids=item.knowledge_ids,
        payload=item.payload,  # jamais la solution
        attempt=attempt_summary(attempt),
    )


async def session_out(db: DbSession, revision: RevisionSession) -> SessionOut:
    items = await learning.session_items(db, revision)
    attempts = await learning.attempts_by_item(db, revision)
    blocks = {i.block for i in items}
    return SessionOut(
        id=revision.id,
        lesson_id=revision.lesson_id,
        kind=revision.kind,
        status=revision.status,
        objective=revision.objective,
        estimated_duration_min=max(1, -(-revision.estimated_duration_s // 60)),
        express=revision.kind == "review" and Block.CORE not in blocks,
        items=[item_out(i, attempts.get(i.id)) for i in items],
        score_on_10=float(revision.score_on_10) if revision.score_on_10 is not None else None,
    )


async def session_of_child(db: DbSession, child: Child, session_id: uuid.UUID) -> RevisionSession:
    revision = await db.scalar(
        select(RevisionSession).where(RevisionSession.id == session_id, RevisionSession.child_id == child.id)
    )
    if revision is None:
        raise ApiError(404, "session_not_found", "Séance introuvable.")
    return revision


@router.post("/lessons/{lesson_id}/sessions")
async def start_session(
    lesson_id: uuid.UUID,
    body: SessionCreate,
    child: ChildInScope,
    db: DbSession,
    registry: Registry,
    settings: AppSettings,
) -> SessionOut:
    """Écran 4 : séance adaptée à la maîtrise de l'enfant (ou reprise de la séance en cours), à la
    durée choisie par le parent et, pendant un plan avant un contrôle, à l'étape du jour."""
    lesson = await lesson_of_child(db, child, lesson_id)
    now = clock.now()
    options = await goals.session_options(db, child, lesson.id, now, ZoneInfo(settings.family_timezone))
    try:
        revision = await learning.start_session(db, child.id, lesson, registry, now, options)
    except learning.LessonNotReady as exc:
        raise ApiError(409, "lesson_not_ready", "La leçon n'est pas encore prête.") from exc
    except NothingToReview as exc:
        raise NOTHING_TO_REVIEW from exc
    await db.commit()
    return await session_out(db, revision)


@router.get("/sessions/{session_id}")
async def get_session(session_id: uuid.UUID, child: ChildInScope, db: DbSession) -> SessionOut:
    return await session_out(db, await session_of_child(db, child, session_id))


async def item_of_session(db: DbSession, revision: RevisionSession, item_id: uuid.UUID) -> SessionItem:
    item = await db.scalar(
        select(SessionItem).where(SessionItem.id == item_id, SessionItem.session_id == revision.id)
    )
    if item is None:
        raise ApiError(404, "item_not_found", "Activité introuvable dans cette séance.")
    return item


async def evaluator_within_budget(db: DbSession, settings: AppSettings, ai: Ai) -> AnswerEvaluator | None:
    """Correcteur IA des réponses rédigées ; aucun si le plafond de coût du jour est atteint."""
    if await ai_budget.seconds_until_budget(db, settings.ai_daily_budget_usd, clock.now()) is not None:
        return None
    return AnswerEvaluator(ai.llm)


@router.post("/sessions/{session_id}/attempts")
async def submit_attempt(
    session_id: uuid.UUID,
    body: AttemptIn,
    child: ChildInScope,
    db: DbSession,
    registry: Registry,
    settings: AppSettings,
    ai: Ai,
) -> AttemptOut:
    """Écran 6 : correction immédiate, avec l'astuce et l'explication. Une question ouverte est
    corrigée par l'IA (quelques secondes), ou par ses mots clés si l'IA n'est pas disponible."""
    revision = await session_of_child(db, child, session_id)
    item = await item_of_session(db, revision, body.item_id)
    evaluator = (
        await evaluator_within_budget(db, settings, ai)
        if item.activity_type == ActivityCode.OPEN_QUESTION
        else None
    )
    try:
        grade = await learning.answer(
            db, revision, item, body.response, body.duration_ms, registry, clock.now(), evaluator
        )
    except learning.SessionClosed as exc:
        raise SESSION_CLOSED from exc
    except learning.AlreadyAnswered as exc:
        raise ApiError(409, "already_answered", "Cette activité a déjà une réponse.") from exc
    except InvalidResponse as exc:
        raise ApiError(422, "invalid_response", f"Réponse invalide : {exc}") from exc
    try:
        await db.commit()
    except IntegrityError as exc:  # double envoi simultané de la même réponse
        await db.rollback()
        raise ApiError(409, "already_answered", "Cette activité a déjà une réponse.") from exc
    if grade is None:
        return AttemptOut(
            item_id=item.id, result="skipped", score=0, correct_answer=None, tip=None, explanation=None
        )
    return AttemptOut(
        item_id=item.id,
        result=grade.result,
        score=grade.score,
        correct_answer=grade.correct_answer,
        tip=grade.tip,
        explanation=grade.explanation,
        details=grade.details,
    )


@router.post("/sessions/{session_id}/items/{item_id}/help")
async def get_help(
    session_id: uuid.UUID, item_id: uuid.UUID, child: ChildInScope, db: DbSession, registry: Registry
) -> HelpOut:
    """« ❓ Je n'ai pas compris » : chaque appel donne l'aide suivante (indice, rappel, exemple,
    étapes, puis la réponse). L'aide ne change pas la note, seulement la maîtrise (§5.4)."""
    revision = await session_of_child(db, child, session_id)
    item = await item_of_session(db, revision, item_id)
    try:
        step = await learning.request_help(db, revision, item, registry)
    except learning.SessionClosed as exc:
        raise SESSION_CLOSED from exc
    except learning.AlreadyAnswered as exc:
        raise ApiError(409, "already_answered", "Cette activité a déjà une réponse.") from exc
    except learning.HelpUnavailable as exc:
        raise ApiError(
            409, "help_unavailable", "Pas d'aide pour ce jeu : essaie, tu verras la correction."
        ) from exc
    await db.commit()
    return HelpOut(
        level=step.level,
        kind=step.kind.value,
        title=step.title,
        text=step.text,
        lines=step.lines,
        last=step.last,
    )


@router.post("/sessions/{session_id}/replay")
async def replay(session_id: uuid.UUID, child: ChildInScope, db: DbSession, registry: Registry) -> ReplayOut:
    """🔄 Reprise des erreurs, après la dernière activité principale (liste vide s'il n'y en a pas)."""
    revision = await session_of_child(db, child, session_id)
    try:
        items = await learning.add_replay(db, revision, registry)
    except learning.SessionClosed as exc:
        raise SESSION_CLOSED from exc
    except learning.MainNotFinished as exc:
        raise ApiError(409, "session_not_finished", "Termine d'abord les activités de la séance.") from exc
    await db.commit()
    attempts = await learning.attempts_by_item(db, revision)
    return ReplayOut(items=[item_out(i, attempts.get(i.id)) for i in items])


@router.post("/sessions/{session_id}/complete")
async def complete(session_id: uuid.UUID, child: ChildInScope, db: DbSession) -> ReportOut:
    """Écran 7 : bilan, nouvelles maîtrises et prochaine révision."""
    revision = await session_of_child(db, child, session_id)
    try:
        done = await learning.complete(db, revision, clock.now())
    except learning.SessionClosed as exc:
        raise SESSION_CLOSED from exc
    await db.commit()
    outcome, lesson = done.outcome, done.lesson
    labels = {u.id: u.item.label for u in lesson.units}
    return ReportOut(
        session_id=revision.id,
        score_on_10=outcome.score_on_10,
        counts={s.value: outcome.count(s) for s in KnowledgeStatus},
        knowledge=[
            KnowledgeResultOut(
                id=lesson.key_to_id[r.knowledge_id],
                label=labels[r.knowledge_id],
                status=r.status.value,
                session_rate=round(r.session_rate, 2),
                mastery=r.mastery.score,
                level=r.level.level,
                previous_level=r.previous_level.level,
                explanation=r.level.explanation,
            )
            for r in outcome.results
        ],
        next_review_at=outcome.next_review_at,
        lesson_mastered=outcome.lesson_mastered,
        can_review_errors=outcome.can_review_errors,
    )


@router.post("/sessions/{session_id}/errors-session", status_code=status.HTTP_201_CREATED)
async def errors_session(
    session_id: uuid.UUID, child: ChildInScope, db: DbSession, registry: Registry
) -> SessionOut:
    """« Revoir mes erreurs » depuis le bilan."""
    origin = await session_of_child(db, child, session_id)
    try:
        revision = await learning.start_errors_session(db, origin, registry, clock.now())
    except learning.SessionClosed as exc:
        raise ApiError(409, "session_not_completed", "Termine d'abord la séance.") from exc
    except NothingToReview as exc:
        raise ApiError(409, "no_errors", "Aucune erreur à revoir : bravo !") from exc
    await db.commit()
    return await session_out(db, revision)
