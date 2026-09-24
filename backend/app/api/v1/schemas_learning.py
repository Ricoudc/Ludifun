"""Formats de l'API v1 pour les leçons, les séances et la mission du jour (§11)."""

import json
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.knowledge import Grade, SkillVerb

StepState = Literal["pending", "running", "done"]


class LessonAccepted(BaseModel):
    id: uuid.UUID
    status: str


Level = int  # niveau de maîtrise affiché, 0 (jamais travaillée) à 5 (très bien maîtrisée)


class KnowledgeOut(BaseModel):
    id: uuid.UUID
    label: str
    statement: str
    importance: int
    type: str
    level: Level = Field(0, description="Niveau de maîtrise de l'enfant, 0 à 5.")


class SkillOut(BaseModel):
    """Une compétence de la leçon (« Comparer deux fractions »)."""

    id: uuid.UUID
    label: str
    verb: SkillVerb
    importance: int
    level: Level = Field(description="Niveau de la compétence, d'après celui de ses notions.")
    knowledge_ids: list[uuid.UUID]


class LessonSummaryOut(BaseModel):
    """Une ligne de l'accueil (écran 1)."""

    id: uuid.UUID
    status: str
    failure_reason: str | None
    subject: str | None
    title: str | None
    created_at: datetime
    next_review_at: datetime | None = None
    due: bool = False
    mastered: bool = False


class LessonOut(LessonSummaryOut):
    """Écrans 3 (statut et étapes) et 4 (leçon et notions)."""

    steps: dict[str, StepState] | None = Field(description="Étapes de l'analyse ; null si échec.")
    failure_message: str | None = None
    grade: str | None = None
    objective: str | None = None
    summary: str | None = None
    knowledge: list[KnowledgeOut] = []
    skills: list[SkillOut] = Field([], description="Vide pour une leçon analysée avant l'étape 13.")
    can_retry: bool = False


class LessonPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grade: Grade


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["auto"] = "auto"


class AttemptSummary(BaseModel):
    result: Literal["correct", "partial", "incorrect", "skipped"]
    score: float


class SessionItemOut(BaseModel):
    id: uuid.UUID
    position: int
    block: str
    type: str
    difficulty: int
    knowledge_ids: list[uuid.UUID]
    payload: dict[str, Any]
    attempt: AttemptSummary | None = Field(None, description="Réponse déjà donnée (reprise d'une séance).")
    help_available: bool = Field(True, description="Bouton « Je n'ai pas compris » proposé.")
    help_level: int = Field(0, description="Aide déjà demandée pour cette activité (0 à 5).")


class SessionOut(BaseModel):
    id: uuid.UUID
    lesson_id: uuid.UUID
    kind: str
    status: str
    objective: str
    estimated_duration_min: int
    express: bool
    items: list[SessionItemOut]
    score_on_10: float | None = None


MAX_RESPONSE_BYTES = 16_000


class AttemptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: uuid.UUID
    response: dict[str, Any]
    duration_ms: int | None = Field(None, ge=0, le=3_600_000)

    @field_validator("response")
    @classmethod
    def _bounded(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(value, ensure_ascii=False)) > MAX_RESPONSE_BYTES:
            raise ValueError("réponse trop volumineuse")
        return value


class AttemptOut(BaseModel):
    """Écran 6 : correction immédiate."""

    item_id: uuid.UUID
    result: Literal["correct", "partial", "incorrect", "skipped"]
    score: float
    correct_answer: str | None
    tip: str | None
    explanation: str | None
    details: list[dict[str, Any]] = []


class HelpOut(BaseModel):
    """« Je n'ai pas compris » : l'aide suivante. Avant le niveau 5, jamais la réponse."""

    level: int = Field(description="1 indice, 2 rappel, 3 exemple, 4 étapes, 5 la réponse.")
    kind: Literal["hint", "reminder", "example", "steps", "answer"]
    title: str
    text: str
    lines: list[str] = Field(description="Étapes, ou réponse et explication de l'exemple.")
    last: bool = Field(description="Plus d'aide après celle-ci.")


class ReplayOut(BaseModel):
    items: list[SessionItemOut]


class KnowledgeResultOut(BaseModel):
    id: uuid.UUID
    label: str
    status: Literal["mastered", "to_review", "not_mastered"]
    session_rate: float
    mastery: int
    level: Level = Field(description="Niveau de maîtrise après la séance, 0 à 5.")
    previous_level: Level = Field(description="Niveau avant la séance.")
    explanation: str = Field(description="Pourquoi ce niveau (ce qui manque encore).")


class ReportOut(BaseModel):
    """Écran 7 : bilan."""

    session_id: uuid.UUID
    score_on_10: float
    counts: dict[str, int]
    knowledge: list[KnowledgeResultOut]
    next_review_at: datetime | None
    lesson_mastered: bool
    can_review_errors: bool


class MissionLesson(BaseModel):
    id: uuid.UUID
    title: str | None
    subject: str | None


class MissionOut(BaseModel):
    lesson: MissionLesson | None
    reason: Literal["due", "not_mastered", "latest"] | None = None
    estimated_minutes: int | None = None
