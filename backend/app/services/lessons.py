"""Pipeline « photo → leçon structurée → banque de questions »."""

from sqlmodel import Session, select

from app.ai.client import LLM, LessonImage
from app.ai.schemas import GeneratedQuestion
from app.models import Answer, Child, Lesson, Notion, NotionMastery, Question, RevisionSession


class UnreadableLesson(ValueError):
    pass


def _is_valid(q: GeneratedQuestion, notion_count: int) -> bool:
    """Écarte les questions mal formées plutôt que de montrer une erreur à l'enfant."""
    if not 0 <= q.notion_index < notion_count or not q.prompt.strip() or not q.answer.strip():
        return False
    if q.kind == "qcm":
        return len(q.choices) >= 2 and q.answer in q.choices
    if q.kind == "vrai_faux":
        return q.answer in ("Vrai", "Faux")
    if q.kind == "texte_a_trous":
        return "___" in q.prompt
    if q.kind == "association":
        return len(q.pairs) >= 2
    return True


def create_lesson(
    db: Session,
    llm: LLM,
    child: Child,
    images: list[LessonImage],
    text: str | None,
    questions_per_notion: int,
) -> Lesson:
    analysis = llm.analyze_lesson(images, text)
    if not analysis.readable or not analysis.notions:
        raise UnreadableLesson("Je n'arrive pas à lire cette leçon. Essaie une photo plus nette.")

    generated = [
        q for q in llm.generate_questions(analysis, questions_per_notion)
        if _is_valid(q, len(analysis.notions))
    ]

    lesson = Lesson(
        child_id=child.id,
        subject=analysis.subject,
        grade=analysis.grade or child.grade,
        title=analysis.title,
        summary=analysis.summary,
        source_text=analysis.source_text,
    )
    db.add(lesson)
    db.flush()

    notions = [
        Notion(lesson_id=lesson.id, label=n.label, kind=n.kind, content=n.content, importance=n.importance)
        for n in analysis.notions
    ]
    db.add_all(notions)
    db.flush()

    for q in generated:
        db.add(
            Question(
                lesson_id=lesson.id,
                notion_id=notions[q.notion_index].id,
                kind=q.kind,
                difficulty=max(1, min(4, q.difficulty)),
                prompt=q.prompt,
                choices=q.choices,
                answer=q.answer,
                explanation=q.explanation,
                pairs=[p.model_dump() for p in q.pairs],
            )
        )
    db.commit()
    db.refresh(lesson)
    return lesson


def delete_lesson(db: Session, lesson: Lesson) -> None:
    notion_ids = db.exec(select(Notion.id).where(Notion.lesson_id == lesson.id)).all()
    session_ids = db.exec(select(RevisionSession.id).where(RevisionSession.lesson_id == lesson.id)).all()
    for model, column, ids in (
        (Answer, Answer.session_id, session_ids),
        (RevisionSession, RevisionSession.id, session_ids),
        (NotionMastery, NotionMastery.notion_id, notion_ids),
        (Question, Question.lesson_id, [lesson.id]),
        (Notion, Notion.id, notion_ids),
    ):
        for row in db.exec(select(model).where(column.in_(ids))).all():
            db.delete(row)
        db.flush()  # respecte l'ordre des clés étrangères (PostgreSQL)
    db.delete(lesson)
    db.commit()
