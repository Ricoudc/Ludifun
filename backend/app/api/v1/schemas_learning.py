"""Formats de l'API v1 pour les leçons, les séances et la mission du jour (§11)."""

import json
import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.v1.schemas_rewards import RewardsOut
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
    source_excerpt: str | None = Field(
        None, description="« Pourquoi cette notion ? » : la phrase de la leçon d'où elle vient (§116)."
    )
    source_page: int | None = Field(None, description="Page de la leçon (1, 2…) où se trouve la phrase.")


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


class ReviewItemOut(BaseModel):
    """« Peux-tu vérifier ? » : un passage que la lecture de la photo n'est pas sûre d'avoir bien lu."""

    id: uuid.UUID
    page_index: int
    read_text: str = Field(description="Ce qui a été lu (ou « [illisible] »).")
    context: str = Field(description="Les mots autour, pour retrouver le passage sur le cahier.")


class LessonTextIn(BaseModel):
    """Leçon collée ou tapée (cahier des charges complet §8.5)."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=40_000)


class ReviewAnswerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: uuid.UUID
    status: Literal["confirmed", "corrected", "unknown"]
    text: str | None = Field(None, max_length=120, description="Le bon mot, pour « corrected ».")


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: list[ReviewAnswerIn] = Field(max_length=10)


class AiStepOut(BaseModel):
    stage: str = Field(description="Étape, en clair (« lecture de la leçon »).")
    model: str
    seconds: int = Field(description="Durée ; pour l'étape en cours, depuis quand elle tourne.")
    status: Literal["ok", "running", "error", "invalid_output", "refused"]
    message: str | None = Field(None, description="Message de l'IA en cas d'erreur (sans texte de leçon).")


class DiagnosticsOut(BaseModel):
    """« Voir ce qui se passe » : l'IA au travail, étape par étape."""

    steps: list[AiStepOut]
    explanation: str | None = Field(None, description="Raison de l'échec, en clair (pour le parent).")


class LessonOut(LessonSummaryOut):
    """Écrans 3 (statut et étapes) et 4 (leçon et notions)."""

    steps: dict[str, StepState] | None = Field(description="Étapes de l'analyse ; null si échec.")
    failure_message: str | None = None
    grade: str | None = None
    objective: str | None = None
    summary: str | None = None
    knowledge: list[KnowledgeOut] = []
    skills: list[SkillOut] = Field([], description="Vide pour une leçon analysée avant l'étape 13.")
    source: Literal["photo", "text"] = "photo"
    review: list[ReviewItemOut] = Field([], description="Passages à vérifier (statut `needs_review`).")
    can_retry: bool = False
    diagnostics: DiagnosticsOut | None = None


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
    intro: str | None = Field(None, description="À afficher avant l'activité (rappel de la règle).")


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


class EngagementHintOut(BaseModel):
    kind: Literal["fast_guessing", "struggling"]
    message: str


class AttemptOut(BaseModel):
    """Écran 6 : correction immédiate."""

    item_id: uuid.UUID
    result: Literal["correct", "partial", "incorrect", "skipped"]
    score: float
    correct_answer: str | None
    tip: str | None
    explanation: str | None
    details: list[dict[str, Any]] = []
    inserted_items: list[SessionItemOut] = Field(
        [], description="Remédiation : activités à jouer juste après celle-ci (déjà en place dans la séance)."
    )
    engagement_hint: EngagementHintOut | None = Field(None, description="Proposition de pause.")


class HelpOut(BaseModel):
    """« Je n'ai pas compris » : l'aide suivante. Avant le niveau 5, jamais la réponse."""

    level: int = Field(description="1 indice, 2 rappel, 3 exemple, 4 étapes, 5 la réponse.")
    kind: Literal["hint", "reminder", "example", "steps", "answer", "sourced"]
    title: str
    text: str
    lines: list[str] = Field(description="Étapes, ou réponse et explication de l'exemple.")
    last: bool = Field(description="Plus d'aide après celle-ci.")


class ReplayOut(BaseModel):
    items: list[SessionItemOut]
    bonus_offer: bool = Field(False, description="Proposer « encore 3 défis ? » (séance réussie et rapide).")


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
    rewards: RewardsOut | None = Field(None, description="XP, badges et message (étape 20).")


class MissionLesson(BaseModel):
    id: uuid.UUID
    title: str | None
    subject: str | None


class MissionExam(BaseModel):
    title: str
    exam_date: date
    focus: str = Field(description="diagnostic, targeted, memorize, errors ou mock_test.")
    focus_label: str


class MissionOut(BaseModel):
    lesson: MissionLesson | None
    reason: Literal["exam", "due", "not_mastered", "latest"] | None = None
    estimated_minutes: int | None = None
    exam: MissionExam | None = Field(None, description="Étape du jour du plan avant un contrôle.")
    daily_minutes: int | None = Field(None, description="Temps de révision par jour choisi par le parent.")
