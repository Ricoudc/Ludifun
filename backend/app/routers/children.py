from collections import defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.db import get_session
from app.models import Answer, Child, Lesson, Notion, NotionMastery, RevisionSession, utcnow
from app.schemas import (
    ChildCreate,
    ChildOut,
    ChildProgress,
    LessonListItem,
    NotionProgress,
    SubjectProgress,
)
from app.services import lessons as lesson_service
from app.services.mastery import LEVEL_LABELS

router = APIRouter(prefix="/children", tags=["enfants"])


def get_child_or_404(child_id: int, db: Session) -> Child:
    child = db.get(Child, child_id)
    if child is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enfant introuvable.")
    return child


@router.post("", response_model=ChildOut, status_code=status.HTTP_201_CREATED)
def create_child(body: ChildCreate, db: Session = Depends(get_session)) -> Child:
    child = Child(display_name=body.display_name.strip(), grade=body.grade)
    db.add(child)
    db.commit()
    db.refresh(child)
    return child


@router.get("/{child_id}", response_model=ChildOut)
def read_child(child_id: int, db: Session = Depends(get_session)) -> Child:
    return get_child_or_404(child_id, db)


@router.delete("/{child_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_child(child_id: int, db: Session = Depends(get_session)) -> None:
    """Droit à l'effacement : supprime l'enfant et toutes ses données."""
    child = get_child_or_404(child_id, db)
    for lesson in db.exec(select(Lesson).where(Lesson.child_id == child.id)).all():
        lesson_service.delete_lesson(db, lesson)
    db.delete(child)
    db.commit()


@router.get("/{child_id}/lessons", response_model=list[LessonListItem])
def list_lessons(child_id: int, db: Session = Depends(get_session)) -> list[Lesson]:
    get_child_or_404(child_id, db)
    return db.exec(
        select(Lesson).where(Lesson.child_id == child_id).order_by(Lesson.created_at.desc())
    ).all()


@router.get("/{child_id}/progress", response_model=ChildProgress)
def progress(child_id: int, db: Session = Depends(get_session)) -> ChildProgress:
    """Tableau de bord : progression de l'enfant par rapport à lui-même."""
    child = get_child_or_404(child_id, db)
    now = utcnow()
    lessons = {l.id: l for l in db.exec(select(Lesson).where(Lesson.child_id == child.id)).all()}
    sessions = db.exec(select(RevisionSession).where(RevisionSession.child_id == child.id)).all()
    session_lesson = {s.id: s.lesson_id for s in sessions}
    answers = db.exec(
        select(Answer).where(Answer.session_id.in_(list(session_lesson)))
    ).all() if session_lesson else []

    by_subject: dict[str, list[float]] = defaultdict(list)
    for a in answers:
        by_subject[lessons[session_lesson[a.session_id]].subject].append(a.score)

    week_ago = now - timedelta(days=7)
    minutes = sum(
        ((s.finished_at or s.started_at) - s.started_at).total_seconds() / 60
        for s in sessions
        if s.started_at >= week_ago
    )

    rows = db.exec(
        select(NotionMastery, Notion)
        .join(Notion, Notion.id == NotionMastery.notion_id)
        .where(NotionMastery.child_id == child.id)
    ).all()
    notions = [
        NotionProgress(
            notion_id=n.id,
            lesson_id=n.lesson_id,
            label=n.label,
            level=m.level,
            level_label=LEVEL_LABELS[m.level],
            next_review_at=m.next_review_at,
        )
        for m, n in rows
    ]

    return ChildProgress(
        child=ChildOut(**child.model_dump()),
        lessons=len(lessons),
        total_answers=len(answers),
        success_rate=round(sum(a.score for a in answers) / len(answers), 2) if answers else 0.0,
        minutes_last_7_days=round(minutes, 1),
        subjects=[
            SubjectProgress(subject=s, success_rate=round(sum(v) / len(v), 2), answers=len(v))
            for s, v in sorted(by_subject.items())
        ],
        to_strengthen=sorted([p for p in notions if p.level <= 3], key=lambda p: p.level),
        due_reviews=sorted(
            [p for p in notions if p.next_review_at and p.next_review_at <= now],
            key=lambda p: p.next_review_at,
        ),
    )
