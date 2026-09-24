"""Formats de l'API v1 pour l'espace parent : tableau de bord et historique (§11)."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.knowledge import SkillVerb


class WeekOut(BaseModel):
    week_start: date = Field(description="Lundi de la semaine, à l'heure de la famille.")
    sessions: int = Field(description="Séances terminées.")
    minutes: int = Field(description="Temps de révision (réponses plafonnées à 5 min + 8 s de correction).")
    average_score: float | None = Field(description="Note moyenne sur 10 des séances terminées.")


class SubjectOut(BaseModel):
    subject: str
    mastery: int = Field(
        description="Maîtrise moyenne (0-100) des notions travaillées, pondérée par importance."
    )
    color: Literal["green", "orange", "red"]
    notions: int


class WeakNotionOut(BaseModel):
    knowledge_id: uuid.UUID
    label: str
    lesson_id: uuid.UUID
    lesson_title: str | None
    subject: str | None
    mastery: int
    status: Literal["to_review", "not_mastered"]
    next_review_at: datetime
    level: int = Field(description="Niveau de maîtrise, 0 à 5 (3 : en cours d'acquisition).")
    explanation: str = Field(description="Ce qui manque encore, en une phrase.")


class DashboardOut(BaseModel):
    """Écran P3."""

    child_id: uuid.UUID
    timezone: str
    this_week: WeekOut
    lessons_added_this_week: int
    activities_this_week: dict[str, int]
    subjects: list[SubjectOut]
    to_strengthen: list[WeakNotionOut] = Field(
        description="Au plus 5 notions pas encore maîtrisées (niveau ≤ 3), les plus faibles d'abord."
    )
    reviews_due: int = Field(description="Notions dont la révision est due maintenant.")
    weeks: list[WeekOut] = Field(description="De la plus ancienne à la semaine en cours.")
    trend: Literal["up", "down", "stable"] | None = Field(
        description="Note moyenne des deux dernières semaines actives (±0,5)."
    )


class NotionResultOut(BaseModel):
    label: str
    status: Literal["mastered", "to_review", "not_mastered"]


class HistoryEntryOut(BaseModel):
    session_id: uuid.UUID
    lesson_id: uuid.UUID
    lesson_title: str | None
    subject: str | None
    kind: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    minutes: int
    score_on_10: float | None
    notions: list[NotionResultOut] = Field(
        description="Résultat de la séance par notion (séances terminées)."
    )


class HistoryOut(BaseModel):
    """Écran P4."""

    sessions: list[HistoryEntryOut]
    next_before: datetime | None


Color = Literal["grey", "red", "orange", "green"]


class LevelOut(BaseModel):
    value: int = Field(
        description="0 jamais travaillée, 1 découverte, 2 fragile, 3 en cours, 4 maîtrisée, 5 très bien."
    )
    label: str
    color: Color


class NotionProgressOut(BaseModel):
    id: uuid.UUID
    label: str
    importance: int
    level: LevelOut
    explanation: str


class SkillProgressOut(BaseModel):
    id: uuid.UUID
    label: str
    verb: SkillVerb
    importance: int
    level: LevelOut
    knowledge_ids: list[uuid.UUID]


class LessonProgressOut(BaseModel):
    lesson_id: uuid.UUID
    title: str | None
    subject: str | None
    created_at: datetime
    skills: list[SkillProgressOut] = Field(description="Vide pour une leçon analysée avant l'étape 13.")
    notions: list[NotionProgressOut]


class SkillsOut(BaseModel):
    """Compétences et notions, leçon par leçon."""

    lessons: list[LessonProgressOut] = Field(description="Les 20 leçons prêtes les plus récentes.")
