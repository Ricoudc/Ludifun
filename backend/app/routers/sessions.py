from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.ai.client import LLM, LLMError
from app.db import get_session
from app.deps import get_llm
from app.models import Answer, Child, Notion, NotionMastery, Question, RevisionSession, utcnow
from app.schemas import AnswerIn, AnswerResult, NotionResult, SessionReport
from app.services import mastery
from app.services.evaluator import evaluate

router = APIRouter(prefix="/sessions", tags=["séances"])


def get_open_session(session_id: int, db: Session) -> RevisionSession:
    session = db.get(RevisionSession, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Séance introuvable.")
    if session.finished_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Séance déjà terminée.")
    return session


@router.post("/{session_id}/answers", response_model=AnswerResult)
def submit_answer(
    session_id: int,
    body: AnswerIn,
    db: Session = Depends(get_session),
    llm: LLM = Depends(get_llm),
) -> AnswerResult:
    session = get_open_session(session_id, db)
    if body.question_id not in session.question_ids:
        raise HTTPException(422, "Cette question ne fait pas partie de la séance.")
    already = db.exec(
        select(Answer).where(Answer.session_id == session.id, Answer.question_id == body.question_id)
    ).first()
    if already is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Question déjà répondue.")

    question = db.get(Question, body.question_id)
    child = db.get(Child, session.child_id)
    try:
        result = evaluate(question, body.answer, llm, child.grade)
    except LLMError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    db.add(
        Answer(
            session_id=session.id,
            question_id=question.id,
            notion_id=question.notion_id,
            given=body.answer,
            score=result.score,
            correct=result.correct,
            time_ms=body.time_ms,
        )
    )
    db.commit()
    return AnswerResult(
        correct=result.correct,
        score=result.score,
        feedback=result.feedback,
        expected=result.expected,
        missing_points=result.missing_points,
    )


def _message(score_on_10: float) -> str:
    if score_on_10 >= 8:
        return "🎉 Bravo ! Tu maîtrises bien cette leçon."
    if score_on_10 >= 5:
        return "👍 Bien joué ! Encore un petit effort sur les notions à renforcer."
    return "💪 Courage ! On va retravailler ensemble les notions à revoir."


@router.post("/{session_id}/finish", response_model=SessionReport)
def finish_session(session_id: int, db: Session = Depends(get_session)) -> SessionReport:
    """Clôt la séance, met à jour la maîtrise de chaque notion et programme les rappels."""
    session = get_open_session(session_id, db)
    answers = db.exec(select(Answer).where(Answer.session_id == session.id)).all()
    now = utcnow()

    scores: dict[int, list[float]] = defaultdict(list)
    for a in answers:
        scores[a.notion_id].append(a.score)

    results: list[NotionResult] = []
    for notion_id, notion_scores in scores.items():
        rate = sum(notion_scores) / len(notion_scores)
        record = db.exec(
            select(NotionMastery).where(
                NotionMastery.child_id == session.child_id, NotionMastery.notion_id == notion_id
            )
        ).first() or NotionMastery(child_id=session.child_id, notion_id=notion_id)
        record.level = mastery.next_level(record.level, rate)
        record.last_reviewed_at = now
        record.next_review_at = mastery.next_review(record.level, now)
        db.add(record)

        notion = db.get(Notion, notion_id)
        results.append(
            NotionResult(
                notion_id=notion_id,
                label=notion.label,
                success_rate=round(rate, 2),
                status=mastery.status(rate),
                level=record.level,
                level_label=mastery.LEVEL_LABELS[record.level],
                next_review_at=record.next_review_at,
            )
        )

    session.finished_at = now
    db.add(session)
    db.commit()

    correct = sum(1 for a in answers if a.correct)
    score_on_10 = round(10 * sum(a.score for a in answers) / len(answers), 1) if answers else 0.0
    results.sort(key=lambda r: r.success_rate)
    return SessionReport(
        session_id=session.id,
        answered=len(answers),
        correct=correct,
        score_on_10=score_on_10,
        notions=results,
        message=_message(score_on_10),
    )
