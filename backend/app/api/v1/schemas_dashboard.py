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


class ErrorCountOut(BaseModel):
    error_type: str
    label: str = Field(description="Ce que l'erreur dit de l'enfant (« Confond avec une autre notion »).")
    count: int


class RecurringErrorOut(BaseModel):
    knowledge_id: uuid.UUID
    label: str
    lesson_title: str | None
    error_type: str
    error_label: str
    sessions: int = Field(description="Séances où cette erreur est revenue sur cette notion.")
    last_at: datetime


class DashboardOut(BaseModel):
    """Écran P3."""

    child_id: uuid.UUID
    timezone: str
    this_week: WeekOut
    lessons_added_this_week: int
    help_this_week: int = Field(0, description="Questions où l'enfant a demandé de l'aide cette semaine.")
    reports_to_see: int = Field(0, description="Questions signalées par l'enfant (🚩), pas encore vues.")
    summary: list[str] = Field(
        [], description="« En bref » : les 7 derniers jours en quelques phrases, la dernière est un conseil."
    )
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
    error_types: list[ErrorCountOut] = Field(
        [], description="Types des erreurs des 30 derniers jours, les plus fréquents d'abord."
    )
    recurring_errors: list[RecurringErrorOut] = Field(
        [], description="Au plus 5 : même erreur sur la même notion dans 3 séances (60 derniers jours)."
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


class MistakeOut(BaseModel):
    """Une question ratée : ce qui était demandé, ce que l'enfant a répondu, la bonne réponse."""

    answered_at: datetime
    lesson_id: uuid.UUID
    lesson_title: str | None
    subject: str | None
    activity_type: str
    notions: list[str]
    question: str
    given: str = Field(description="La réponse de l'enfant (une ligne par élément raté).")
    expected: str = Field(description="La bonne réponse.")
    partial: bool = Field(description="Réponse en partie juste.")


class HelpStepOut(BaseModel):
    level: int = Field(description="1 indice … 5 la réponse.")
    kind: str = Field(description="hint, reminder, example, steps, answer, sourced.")
    title: str = Field(description="« 💡 Un indice », « ✅ La réponse »…")
    at: datetime


class HelpRequestOut(BaseModel):
    """Une question où l'enfant a touché « Je n'ai pas compris » : quand, les aides vues, la suite."""

    asked_at: datetime = Field(description="Premier appui sur « Je n'ai pas compris ».")
    lesson_id: uuid.UUID
    lesson_title: str | None
    subject: str | None
    activity_type: str
    notions: list[str]
    question: str
    steps: list[HelpStepOut]
    outcome: Literal["right", "partial", "wrong", "unanswered"] = Field(
        description="Réponse donnée après l'aide : juste, en partie, fausse, ou pas de réponse."
    )


class HelpRequestsOut(BaseModel):
    help_requests: list[HelpRequestOut]
    next_before: datetime | None


ReportReason = Literal["right_answer", "unclear", "wrong_question"]
Outcome = Literal["right", "partial", "wrong", "unanswered"]


class QuestionReportOut(BaseModel):
    """Une question signalée par l'enfant (🚩)."""

    id: uuid.UUID
    reported_at: datetime
    reason: ReportReason
    reason_label: str = Field(description="« Ma réponse était juste »…, tel que l'enfant l'a choisi.")
    seen: bool = Field(description="Le parent l'a marquée comme vue.")
    lesson_id: uuid.UUID
    lesson_title: str | None
    subject: str | None
    activity_type: str
    notions: list[str]
    question: str
    given: str | None = Field(
        description="La réponse de l'enfant ; absente s'il a signalé avant de répondre."
    )
    expected: str | None = Field(description="La bonne réponse retenue par Ludifun.")
    outcome: Outcome


class QuestionReportsOut(BaseModel):
    reports: list[QuestionReportOut]
    next_before: datetime | None


class MistakesOut(BaseModel):
    mistakes: list[MistakeOut]
    next_before: datetime | None


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


class LevelRateOut(BaseModel):
    level: int = Field(description="1 reconnaître, 2 se rappeler, 3 appliquer, 4 expliquer, 5 transférer.")
    name: str
    rate: float | None = Field(description="Réussite aux 10 dernières réponses de ce niveau ; null : jamais.")


class NotionProgressOut(BaseModel):
    id: uuid.UUID
    label: str
    importance: int
    level: LevelOut
    explanation: str = Field(description="Interprétation du moteur (d'après le score et les niveaux).")
    facts: str | None = Field(None, description="Fait observé, chiffré (« Sur les 8 dernières activités… »).")
    level_rates: list[LevelRateOut] = Field([], description="Réussite par niveau de compréhension (§114).")
    independence: float | None = Field(None, description="Part des réussites obtenues sans aide (§129).")


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


class SessionActivityOut(BaseModel):
    position: int
    block: str
    activity: str = Field(description="Type d'activité, en clair (« QCM », « Carte »…).")
    difficulty: int
    notions: list[str]
    result: Literal["correct", "partial", "incorrect", "skipped"] | None = Field(
        description="null : pas encore répondu."
    )
    help_level: int = Field(description="Aide la plus forte demandée avant la réponse (0 : seul).")
    reason: str | None = Field(description="Pourquoi le moteur a choisi cette activité (§126).")


class SessionDecisionOut(BaseModel):
    rule: str
    text: str
    position: int | None


class SessionDetailOut(BaseModel):
    """Détail d'une séance pour le parent : chaque activité, son résultat et sa raison."""

    session_id: uuid.UUID
    kind: str
    started_at: datetime
    engine_version: str | None = Field(description="Version des règles du moteur ; null : avant l'étape 23.")
    activities: list[SessionActivityOut]
    decisions: list[SessionDecisionOut] = Field(description="Remédiations, pauses, défis bonus.")


class ProgrammeNotionOut(BaseModel):
    label: str
    lesson_id: uuid.UUID
    lesson_title: str | None
    level: LevelOut


class SubCompetenceOut(BaseModel):
    id: str = Field(description="Identifiant stable dans le référentiel (« MA-07 »).")
    title: str
    grades: list[str] = Field(description="Classes où le programme la place.")
    status: Literal["not_seen", "started", "mastered"] = Field(
        description="Pas encore vue (aucune leçon), commencée, ou maîtrisée (toutes ses notions au "
        "niveau 4 ou plus)."
    )
    notions: list[ProgrammeNotionOut]


class ProgrammeCompetenceOut(BaseModel):
    title: str
    subs: list[SubCompetenceOut]


class ProgrammeDomainOut(BaseModel):
    title: str
    competences: list[ProgrammeCompetenceOut]


class ProgrammeSubjectOut(BaseModel):
    subject: str
    total: int = Field(description="Sous-compétences du programme de la classe dans cette matière.")
    started: int
    mastered: int
    domains: list[ProgrammeDomainOut]
    elsewhere: list[SubCompetenceOut] = Field(
        description="Notions rangées dans le programme d'une autre classe (une leçon revue, ou en avance)."
    )
    unplaced: list[ProgrammeNotionOut] = Field(description="Notions que le référentiel ne range nulle part.")


class ProgrammeOut(BaseModel):
    """Le programme de la classe de l'enfant (§105), et où en sont ses notions."""

    grade: str
    version: str = Field(description="Version du référentiel.")
    source: str
    subjects: list[ProgrammeSubjectOut]
