"""Formats d'entrée / sortie de l'API REST."""

import random
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models import Question

Grade = Literal["CP", "CE1", "CE2", "CM1", "CM2", "6e", "5e", "4e", "3e"]
ModeName = Literal["quiz_rapide", "entrainement", "flashcards", "defi", "revision"]


class ChildCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=40, description="Prénom ou pseudo.")
    grade: Grade


class ChildOut(BaseModel):
    id: int
    display_name: str
    grade: str


class NotionOut(BaseModel):
    id: int
    label: str
    kind: str
    content: str
    importance: str


class LessonOut(BaseModel):
    id: int
    child_id: int
    subject: str
    grade: str
    title: str
    summary: str
    created_at: datetime
    notions: list[NotionOut]
    question_count: int


class LessonListItem(BaseModel):
    id: int
    subject: str
    title: str
    created_at: datetime


class SessionCreate(BaseModel):
    mode: ModeName = "entrainement"


class QuestionOut(BaseModel):
    """Question telle qu'envoyée à l'enfant : sans la bonne réponse."""

    id: int
    notion_id: int
    kind: str
    difficulty: int
    prompt: str
    choices: list[str]
    # Associations : colonne de gauche + colonne de droite mélangée.
    left_items: list[str] = []
    right_items: list[str] = []
    # Flashcards : le verso est nécessaire pour retourner la carte.
    back: str | None = None

    @classmethod
    def from_question(cls, q: Question, rng: random.Random) -> "QuestionOut":
        right = [p["right"] for p in q.pairs]
        rng.shuffle(right)
        return cls(
            id=q.id,
            notion_id=q.notion_id,
            kind=q.kind,
            difficulty=q.difficulty,
            prompt=q.prompt,
            choices=q.choices,
            left_items=[p["left"] for p in q.pairs],
            right_items=right,
            back=q.answer if q.kind == "flashcard" else None,
        )


class SessionOut(BaseModel):
    id: int
    lesson_id: int
    mode: str
    time_limit_s: int | None
    questions: list[QuestionOut]


class AnswerIn(BaseModel):
    question_id: int
    answer: str = Field(max_length=2000)
    time_ms: int | None = Field(default=None, ge=0)


class AnswerResult(BaseModel):
    correct: bool
    score: float
    feedback: str
    expected: str
    missing_points: list[str]


class NotionResult(BaseModel):
    notion_id: int
    label: str
    success_rate: float
    status: Literal["acquis", "a_renforcer", "a_revoir"]
    level: int
    level_label: str
    next_review_at: datetime | None


class SessionReport(BaseModel):
    session_id: int
    answered: int
    correct: int
    score_on_10: float
    notions: list[NotionResult]
    message: str


class SubjectProgress(BaseModel):
    subject: str
    success_rate: float
    answers: int


class NotionProgress(BaseModel):
    notion_id: int
    lesson_id: int
    label: str
    level: int
    level_label: str
    next_review_at: datetime | None


class ChildProgress(BaseModel):
    child: ChildOut
    lessons: int
    total_answers: int
    success_rate: float
    minutes_last_7_days: float
    subjects: list[SubjectProgress]
    to_strengthen: list[NotionProgress]
    due_reviews: list[NotionProgress]
