"""Tables de la base de données.

Principe RGPD : on ne stocke que le strict nécessaire. Un enfant est identifié
par un prénom (ou pseudo) et un niveau scolaire ; les photos des leçons ne sont
jamais écrites sur disque, seul le texte extrait est conservé.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Child(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    display_name: str
    grade: str  # CP … 3e
    created_at: datetime = Field(default_factory=utcnow)


class Lesson(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    child_id: int = Field(foreign_key="child.id", index=True)
    subject: str
    grade: str
    title: str
    summary: str
    source_text: str
    created_at: datetime = Field(default_factory=utcnow)


class Notion(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    lesson_id: int = Field(foreign_key="lesson.id", index=True)
    label: str
    kind: str  # date, vocabulaire, definition, personnage, ...
    content: str
    importance: str  # essentielle, importante, complementaire


class Question(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    lesson_id: int = Field(foreign_key="lesson.id", index=True)
    notion_id: int = Field(foreign_key="notion.id", index=True)
    kind: str  # qcm, vrai_faux, texte_a_trous, flashcard, association, question_ouverte
    difficulty: int  # 1 (reconnaître) … 4 (expliquer)
    prompt: str
    choices: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    answer: str
    explanation: str
    pairs: list[dict] = Field(default_factory=list, sa_column=Column(JSON))


class RevisionSession(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    child_id: int = Field(foreign_key="child.id", index=True)
    lesson_id: int = Field(foreign_key="lesson.id", index=True)
    mode: str
    question_ids: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    time_limit_s: int | None = None
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None


class Answer(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="revisionsession.id", index=True)
    question_id: int = Field(foreign_key="question.id")
    notion_id: int = Field(foreign_key="notion.id")
    given: str
    score: float  # 0.0 … 1.0
    correct: bool
    time_ms: int | None = None
    created_at: datetime = Field(default_factory=utcnow)


class NotionMastery(SQLModel, table=True):
    """Niveau de maîtrise d'une notion par un enfant (0 à 5) + prochaine révision."""

    id: int | None = Field(default=None, primary_key=True)
    child_id: int = Field(foreign_key="child.id", index=True)
    notion_id: int = Field(foreign_key="notion.id", index=True)
    level: int = 0
    next_review_at: datetime | None = None
    last_reviewed_at: datetime | None = None
