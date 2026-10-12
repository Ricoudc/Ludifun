"""Tableau de bord et historique d'un enfant, pour l'espace parent (écrans P3 et P4).

Définitions (affichées telles quelles au parent) :
- **semaine** : du lundi 0 h au dimanche soir, à l'heure de la famille (Europe/Paris par défaut) ;
- **séances** : séances terminées dans la semaine ;
- **temps** : temps passé à répondre (chaque réponse compte au plus 5 minutes, pour ignorer une
  application laissée ouverte), plus 8 secondes par correction lue ;
- **note moyenne** : moyenne des notes sur 10 des séances terminées ;
- **réussite par matière** : maîtrise actuelle des notions travaillées (score 0-100 de §10),
  moyenne pondérée par l'importance des notions ;
- **à renforcer** : notions travaillées pas encore maîtrisées (niveau 3 ou moins sur 5) : score
  sous 80 %, ou niveau de compréhension manquant (réussie en QCM mais jamais retrouvée seul…) ;
- **compétences** : niveau 0 à 5 de chaque compétence de la leçon, d'après ses notions ;
- **erreurs** : types des erreurs des 30 derniers jours, et erreurs récurrentes (même erreur sur
  la même notion dans 3 séances, sur 60 jours).
"""

import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as db
from app.domain.activities.base import ActivityCode, BuiltActivity
from app.domain.errors import ERROR_LABELS, ErrorOccurrence, ErrorType, recurring_errors
from app.domain.knowledge import SkillVerb, Subject
from app.domain.mastery import FRAGILE_RATE, MASTERED_RATE
from app.domain.skill_report import SkillNotion, SkillReport, skill_report
from app.domain.state import NotionState, Observation, notion_state
from app.domain.understanding import MasteryLevel, NotionLevel, notion_level
from app.domain.weekly_summary import RecentFacts, weekly_summary
from app.services.lesson_store import load_masteries, load_skills, load_units, notion_levels, to_mastery

ERROR_TYPES_WINDOW = timedelta(days=30)
RECURRING_WINDOW = timedelta(days=60)
MAX_ANSWER_S = 300
FEEDBACK_S = 8
Color = Literal["green", "orange", "red"]
Trend = Literal["up", "down", "stable"]


def color(percent: float) -> Color:
    """🟢 ≥ 80 %, 🟠 50 à 79 %, 🔴 < 50 % : mêmes seuils que le bilan (§9.3)."""
    if percent >= 100 * MASTERED_RATE:
        return "green"
    if percent >= 100 * FRAGILE_RATE:
        return "orange"
    return "red"


def week_start(moment: datetime, tz: ZoneInfo) -> date:
    local = moment.astimezone(tz).date()
    return local - timedelta(days=local.weekday())


def local_midnight(day: date, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, time.min, tzinfo=tz)


def answer_seconds(duration_ms: int | None) -> float:
    return min((duration_ms or 0) / 1000, MAX_ANSWER_S) + FEEDBACK_S


@dataclass
class WeekStats:
    week_start: date
    sessions: int = 0
    minutes: int = 0
    average_score: float | None = None
    _seconds: float = field(default=0.0, repr=False)
    _scores: list[float] = field(default_factory=list, repr=False)

    def close(self) -> "WeekStats":
        self.minutes = round(self._seconds / 60)
        self.sessions = len(self._scores)
        self.average_score = round(sum(self._scores) / len(self._scores), 1) if self._scores else None
        return self


@dataclass(frozen=True)
class SubjectStats:
    subject: str
    mastery: int
    color: Color
    notions: int


@dataclass(frozen=True)
class WeakNotion:
    knowledge_id: uuid.UUID
    label: str
    lesson_id: uuid.UUID
    lesson_title: str | None
    subject: str | None
    mastery: int
    status: Literal["to_review", "not_mastered"]
    next_review_at: datetime
    level: int
    explanation: str


@dataclass(frozen=True)
class ErrorCount:
    error_type: ErrorType
    count: int


@dataclass(frozen=True)
class RecurringNotion:
    knowledge_id: uuid.UUID
    label: str
    lesson_title: str | None
    error_type: ErrorType
    sessions: int
    last_at: datetime


@dataclass(frozen=True)
class Dashboard:
    this_week: WeekStats
    lessons_added_this_week: int
    subjects: list[SubjectStats]
    to_strengthen: list[WeakNotion]
    due_now: int
    weeks: list[WeekStats]  # de la plus ancienne à la semaine en cours
    trend: Trend | None
    activities: dict[str, int]  # activités réalisées cette semaine, par type
    error_types: list[ErrorCount] = field(default_factory=list)  # les plus fréquentes d'abord
    recurring_errors: list[RecurringNotion] = field(default_factory=list)
    help_this_week: int = 0  # questions où l'enfant a demandé de l'aide cette semaine
    reports_to_see: int = 0  # questions signalées par l'enfant, pas encore vues par le parent
    summary: list[str] = field(default_factory=list)  # « En bref » : les 7 derniers jours


def trend_of(weeks: list[WeekStats]) -> Trend | None:
    scored = [w.average_score for w in weeks if w.average_score is not None]
    if len(scored) < 2:
        return None
    diff = scored[-1] - scored[-2]
    return "up" if diff >= 0.5 else "down" if diff <= -0.5 else "stable"


async def build_dashboard(
    session: AsyncSession, child_id: uuid.UUID, now: datetime, weeks: int, tz: ZoneInfo
) -> Dashboard:
    current = week_start(now, tz)
    starts = [current - timedelta(weeks=i) for i in reversed(range(weeks))]
    stats = {s: WeekStats(s) for s in starts}
    since = local_midnight(starts[0], tz)

    completed = await session.execute(
        select(db.RevisionSession.completed_at, db.RevisionSession.score_on_10).where(
            db.RevisionSession.child_id == child_id,
            db.RevisionSession.status == "completed",
            db.RevisionSession.completed_at >= since,
        )
    )
    for completed_at, score in completed:
        stats[week_start(completed_at, tz)]._scores.append(float(score))

    activities: Counter[str] = Counter()
    attempts = await session.execute(
        select(
            db.Attempt.created_at, db.Attempt.duration_ms, db.Attempt.response, db.SessionItem.activity_type
        )
        .join(db.SessionItem, db.SessionItem.id == db.Attempt.session_item_id)
        .join(db.RevisionSession, db.RevisionSession.id == db.SessionItem.session_id)
        .where(db.RevisionSession.child_id == child_id, db.Attempt.created_at >= since)
    )
    for created_at, duration_ms, response, activity_type in attempts:
        week = week_start(created_at, tz)
        stats[week]._seconds += answer_seconds(duration_ms)
        if week == current and response != {"skipped": True}:
            activities[activity_type] += 1
    closed = [stats[s].close() for s in starts]

    rows = (
        await session.execute(
            select(db.KnowledgeMastery, db.KnowledgeItem, db.Lesson)
            .join(db.KnowledgeItem, db.KnowledgeItem.id == db.KnowledgeMastery.knowledge_id)
            .join(db.Lesson, db.Lesson.id == db.KnowledgeItem.lesson_id)
            .where(db.KnowledgeMastery.child_id == child_id)
        )
    ).all()
    by_subject: dict[str, list[tuple[int, int]]] = defaultdict(list)
    weak = []
    for mastery, item, lesson in rows:
        by_subject[lesson.subject or Subject.OTHER].append((mastery.score, item.importance))
        level = notion_level(to_mastery(mastery), item.required_levels, now)
        if level.level <= MasteryLevel.LEARNING:
            weak.append(
                (
                    (level.level, mastery.score, -item.importance, mastery.next_review_at),
                    WeakNotion(
                        knowledge_id=item.id,
                        label=item.label,
                        lesson_id=lesson.id,
                        lesson_title=lesson.title,
                        subject=lesson.subject,
                        mastery=mastery.score,
                        status="to_review" if level.level == MasteryLevel.LEARNING else "not_mastered",
                        next_review_at=mastery.next_review_at,
                        level=level.level,
                        explanation=level.explanation,
                    ),
                )
            )
    order = {s.value: i for i, s in enumerate(Subject)}
    subjects = []
    for subject in sorted(by_subject, key=lambda s: order.get(s, len(order))):
        scores = by_subject[subject]
        percent = round(sum(s * w for s, w in scores) / sum(w for _, w in scores))
        subjects.append(SubjectStats(subject, percent, color(percent), len(scores)))

    lessons_added = await session.scalar(
        select(func.count())
        .select_from(db.Lesson)
        .where(db.Lesson.child_id == child_id, db.Lesson.created_at >= local_midnight(current, tz))
    )
    due_now = sum(1 for mastery, _, _ in rows if mastery.next_review_at <= now)
    error_types, recurring = await error_summary(session, child_id, now)
    help_this_week = await session.scalar(
        select(func.count(func.distinct(db.HelpRequest.session_item_id)))
        .join(db.SessionItem, db.SessionItem.id == db.HelpRequest.session_item_id)
        .join(db.RevisionSession, db.RevisionSession.id == db.SessionItem.session_id)
        .where(
            db.RevisionSession.child_id == child_id,
            db.HelpRequest.requested_at >= local_midnight(current, tz),
        )
    )
    to_see = await reports_to_see(session, child_id)
    strengthen = [notion for _, notion in sorted(weak, key=lambda w: w[0])[:5]]
    mastered = sorted(
        (
            (-item.importance, item.label)
            for mastery, item, _ in rows
            if mastery.last_practiced_at >= now - RECENT
            and notion_level(to_mastery(mastery), item.required_levels).level >= MasteryLevel.MASTERED
        ),
    )
    facts = await recent_facts(session, child_id, now, tz)
    summary = weekly_summary(
        replace(
            facts,
            mastered=[label for _, label in mastered],
            weak=(strengthen[0].label, strengthen[0].lesson_title) if strengthen else None,
            recurring=(ERROR_LABELS[recurring[0].error_type], recurring[0].label) if recurring else None,
            reports_to_see=to_see,
            reviews_due=due_now,
        )
    )
    return Dashboard(
        summary=summary,
        help_this_week=help_this_week or 0,
        reports_to_see=to_see,
        error_types=error_types,
        recurring_errors=recurring,
        this_week=closed[-1],
        lessons_added_this_week=lessons_added or 0,
        subjects=subjects,
        to_strengthen=strengthen,
        due_now=due_now,
        weeks=closed,
        trend=trend_of(closed),
        activities=dict(activities),
    )


RECENT = timedelta(days=7)


async def recent_facts(
    session: AsyncSession, child_id: uuid.UUID, now: datetime, tz: ZoneInfo
) -> RecentFacts:
    """Les chiffres des 7 derniers jours (et le temps des 7 jours d'avant), pour « En bref »."""
    since = now - RECENT
    days: set[date] = set()
    seconds = previous = 0.0
    for created_at, duration_ms in await session.execute(
        select(db.Attempt.created_at, db.Attempt.duration_ms)
        .join(db.SessionItem, db.SessionItem.id == db.Attempt.session_item_id)
        .join(db.RevisionSession, db.RevisionSession.id == db.SessionItem.session_id)
        .where(db.RevisionSession.child_id == child_id, db.Attempt.created_at >= since - RECENT)
    ):
        if created_at >= since:
            days.add(created_at.astimezone(tz).date())
            seconds += answer_seconds(duration_ms)
        else:
            previous += answer_seconds(duration_ms)
    sessions = await session.scalar(
        select(func.count(db.RevisionSession.id)).where(
            db.RevisionSession.child_id == child_id,
            db.RevisionSession.status == "completed",
            db.RevisionSession.completed_at >= since,
        )
    )
    helped = await session.scalar(
        select(func.count(func.distinct(db.HelpRequest.session_item_id)))
        .join(db.SessionItem, db.SessionItem.id == db.HelpRequest.session_item_id)
        .join(db.RevisionSession, db.RevisionSession.id == db.SessionItem.session_id)
        .where(db.RevisionSession.child_id == child_id, db.HelpRequest.requested_at >= since)
    )
    return RecentFacts(
        days_active=len(days),
        sessions=sessions or 0,
        minutes=round(seconds / 60),
        previous_minutes=round(previous / 60),
        help_questions=helped or 0,
    )


async def error_summary(
    session: AsyncSession, child_id: uuid.UUID, now: datetime
) -> tuple[list[ErrorCount], list[RecurringNotion]]:
    rows = (
        await session.execute(
            select(
                db.AttemptEvidence.knowledge_id,
                db.AttemptEvidence.error_type,
                db.SessionItem.session_id,
                db.Attempt.created_at,
                db.KnowledgeItem.label,
                db.Lesson.title,
            )
            .join(db.Attempt, db.Attempt.id == db.AttemptEvidence.attempt_id)
            .join(db.SessionItem, db.SessionItem.id == db.Attempt.session_item_id)
            .join(db.RevisionSession, db.RevisionSession.id == db.SessionItem.session_id)
            .join(db.KnowledgeItem, db.KnowledgeItem.id == db.AttemptEvidence.knowledge_id)
            .join(db.Lesson, db.Lesson.id == db.KnowledgeItem.lesson_id)
            .where(
                db.RevisionSession.child_id == child_id,
                db.AttemptEvidence.error_type.is_not(None),
                db.Attempt.created_at >= now - RECURRING_WINDOW,
            )
        )
    ).all()
    counts = Counter(ErrorType(error) for _, error, _, at, _, _ in rows if at >= now - ERROR_TYPES_WINDOW)
    names = {knowledge_id: (label, title) for knowledge_id, _, _, _, label, title in rows}
    recurring = recurring_errors(
        ErrorOccurrence(str(knowledge_id), ErrorType(error), str(session_id), at)
        for knowledge_id, error, session_id, at, _, _ in rows
    )
    return (
        [ErrorCount(error, count) for error, count in counts.most_common()],
        [
            RecurringNotion(
                knowledge_id=uuid.UUID(r.knowledge_id),
                label=names[uuid.UUID(r.knowledge_id)][0],
                lesson_title=names[uuid.UUID(r.knowledge_id)][1],
                error_type=r.error_type,
                sessions=r.sessions,
                last_at=r.last_at,
            )
            for r in recurring[:5]
        ],
    )


# --------------------------------------------------------------------------- #
# Compétences et niveaux par leçon
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class NotionProgress:
    knowledge_id: uuid.UUID
    label: str
    importance: int
    level: NotionLevel
    state: NotionState = field(default_factory=lambda: notion_state([]))


@dataclass(frozen=True)
class SkillProgress:
    skill_id: uuid.UUID
    label: str
    verb: str
    importance: int
    level: MasteryLevel
    knowledge_ids: list[uuid.UUID]
    report: SkillReport | None = None  # bilan pour le parent (§5.52)


@dataclass(frozen=True)
class LessonProgress:
    lesson_id: uuid.UUID
    title: str | None
    subject: str | None
    created_at: datetime
    skills: list[SkillProgress]
    notions: list[NotionProgress]  # dans l'ordre de la leçon


async def lessons_progress(
    session: AsyncSession, child_id: uuid.UUID, limit: int, now: datetime | None = None
) -> list[LessonProgress]:
    """Leçons prêtes, de la plus récente à la plus ancienne, avec le niveau de chaque compétence
    et de chaque notion."""
    lessons = list(
        await session.scalars(
            select(db.Lesson)
            .where(db.Lesson.child_id == child_id, db.Lesson.status == "ready")
            .order_by(db.Lesson.created_at.desc())
            .limit(limit)
        )
    )
    skills = await load_skills(session, [lesson.id for lesson in lessons])
    observations = await notion_observations(session, child_id, [lesson.id for lesson in lessons])
    result = []
    for lesson in lessons:
        units = await load_units(session, lesson)
        levels = notion_levels(units, await load_masteries(session, child_id, units), now)
        notions = [
            NotionProgress(
                units.key_to_id[u.id],
                u.item.label,
                u.item.importance,
                levels[units.key_to_id[u.id]],
                notion_state(observations.get(units.key_to_id[u.id], [])),
            )
            for u in units.units
        ]
        by_id = {n.knowledge_id: n for n in notions}
        progress = []
        for skill in skills[lesson.id]:
            level = skill.level(levels)
            own = [by_id[k] for k in skill.knowledge_ids if k in by_id]
            report = skill_report(
                SkillVerb(skill.verb),
                level,
                [SkillNotion(n.label, n.level, n.state) for n in own],
            )
            progress.append(
                SkillProgress(
                    skill.id, skill.label, skill.verb, skill.importance, level, skill.knowledge_ids, report
                )
            )
        result.append(
            LessonProgress(
                lesson_id=lesson.id,
                title=lesson.title,
                subject=lesson.subject,
                created_at=lesson.created_at,
                skills=progress,
                notions=notions,
            )
        )
    return result


async def notion_observations(
    session: AsyncSession, child_id: uuid.UUID, lesson_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[Observation]]:
    """Réponses de l'enfant, notion par notion (état pédagogique, §114)."""
    rows = await session.execute(
        select(
            db.AttemptEvidence.knowledge_id,
            db.Attempt.created_at,
            db.SessionItem.cognitive_level,
            db.AttemptEvidence.result,
            db.Attempt.score,
            db.SessionItem.help_level,
            db.AttemptEvidence.error_type,
        )
        .join(db.Attempt, db.Attempt.id == db.AttemptEvidence.attempt_id)
        .join(db.SessionItem, db.SessionItem.id == db.Attempt.session_item_id)
        .join(db.RevisionSession, db.RevisionSession.id == db.SessionItem.session_id)
        .where(db.RevisionSession.child_id == child_id, db.RevisionSession.lesson_id.in_(lesson_ids))
    )
    by_notion: dict[uuid.UUID, list[Observation]] = defaultdict(list)
    for knowledge_id, at, level, result, score, help_level, error_type in rows:
        by_notion[knowledge_id].append(
            Observation(at, level, float(result), float(score), help_level, error_type)
        )
    return by_notion


# --------------------------------------------------------------------------- #
# Historique (écran P4)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class NotionResult:
    label: str
    status: Literal["mastered", "to_review", "not_mastered"]


@dataclass(frozen=True)
class HistoryEntry:
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
    notions: list[NotionResult]


async def history(
    session: AsyncSession, child_id: uuid.UUID, limit: int, before: datetime | None
) -> list[HistoryEntry]:
    """Séances de la plus récente à la plus ancienne ; `before` pour la page suivante."""
    query = (
        select(db.RevisionSession, db.Lesson)
        .join(db.Lesson, db.Lesson.id == db.RevisionSession.lesson_id)
        .where(db.RevisionSession.child_id == child_id)
        .order_by(db.RevisionSession.started_at.desc())
        .limit(limit)
    )
    if before is not None:
        query = query.where(db.RevisionSession.started_at < before)
    entries = []
    for revision, lesson in (await session.execute(query)).all():
        seconds = sum(
            answer_seconds(duration)
            for duration in await session.scalars(
                select(db.Attempt.duration_ms)
                .join(db.SessionItem, db.SessionItem.id == db.Attempt.session_item_id)
                .where(db.SessionItem.session_id == revision.id)
            )
        )
        notions = []
        if revision.status == "completed":
            rates = await session.execute(
                select(
                    db.KnowledgeItem.label,
                    func.sum(db.AttemptEvidence.result * db.AttemptEvidence.weight)
                    / func.sum(db.AttemptEvidence.weight),
                    func.min(db.KnowledgeItem.importance),
                )
                .join(db.KnowledgeItem, db.KnowledgeItem.id == db.AttemptEvidence.knowledge_id)
                .join(db.Attempt, db.Attempt.id == db.AttemptEvidence.attempt_id)
                .join(db.SessionItem, db.SessionItem.id == db.Attempt.session_item_id)
                .where(db.SessionItem.session_id == revision.id)
                .group_by(db.KnowledgeItem.id, db.KnowledgeItem.label)
            )
            for label, rate, _ in sorted(rates.all(), key=lambda r: (float(r[1]), -r[2])):
                value = float(rate)
                notions.append(
                    NotionResult(
                        label,
                        "mastered"
                        if value >= MASTERED_RATE
                        else "to_review"
                        if value >= FRAGILE_RATE
                        else "not_mastered",
                    )
                )
        entries.append(
            HistoryEntry(
                session_id=revision.id,
                lesson_id=lesson.id,
                lesson_title=lesson.title,
                subject=lesson.subject,
                kind=revision.kind,
                status=revision.status,
                started_at=revision.started_at,
                completed_at=revision.completed_at,
                minutes=round(seconds / 60),
                score_on_10=float(revision.score_on_10) if revision.score_on_10 is not None else None,
                notions=notions,
            )
        )
    return entries


@dataclass(frozen=True)
class MistakeRow:
    answered_at: datetime
    lesson_id: uuid.UUID
    lesson_title: str | None
    subject: str | None
    activity: BuiltActivity
    response: dict[str, Any]
    score: float
    notions: list[str]


async def mistakes(
    session: AsyncSession, child_id: uuid.UUID, limit: int, before: datetime | None
) -> list[MistakeRow]:
    """Réponses pas entièrement justes, de la plus récente à la plus ancienne (bonus compris)."""
    query = (
        select(db.Attempt, db.SessionItem, db.Lesson)
        .join(db.SessionItem, db.SessionItem.id == db.Attempt.session_item_id)
        .join(db.RevisionSession, db.RevisionSession.id == db.SessionItem.session_id)
        .join(db.Lesson, db.Lesson.id == db.RevisionSession.lesson_id)
        .where(db.RevisionSession.child_id == child_id, db.Attempt.score < 1)
        .order_by(db.Attempt.created_at.desc())
        .limit(limit)
    )
    if before is not None:
        query = query.where(db.Attempt.created_at < before)
    found = (await session.execute(query)).all()
    ids = {k for _, item, _ in found for k in item.knowledge_ids}
    knowledge = {
        row.id: (row.key, row.label)
        for row in await session.execute(
            select(db.KnowledgeItem.id, db.KnowledgeItem.key, db.KnowledgeItem.label).where(
                db.KnowledgeItem.id.in_(ids)
            )
        )
    }
    rows = []
    for attempt, item, lesson in found:
        known = [knowledge[k] for k in item.knowledge_ids if k in knowledge]
        activity = BuiltActivity(
            type=ActivityCode(item.activity_type),
            difficulty=item.difficulty,
            knowledge_ids=[key for key, _ in known],
            payload=item.payload,
            solution=item.solution,
        )
        rows.append(
            MistakeRow(
                answered_at=attempt.created_at,
                lesson_id=lesson.id,
                lesson_title=lesson.title,
                subject=lesson.subject,
                activity=activity,
                response=attempt.response,
                score=float(attempt.score),
                notions=[label for _, label in known],
            )
        )
    return rows


@dataclass(frozen=True)
class HelpRow:
    """Une question où l'enfant a demandé de l'aide : quand, les aides vues, et la suite."""

    asked_at: datetime  # premier appui sur « Je n'ai pas compris »
    lesson_id: uuid.UUID
    lesson_title: str | None
    subject: str | None
    activity: BuiltActivity
    notions: list[str]
    steps: list[tuple[int, str, datetime]]  # (niveau, type d'aide, heure), dans l'ordre
    score: float | None  # None : pas (encore) répondu


async def help_requests(
    session: AsyncSession, child_id: uuid.UUID, limit: int, before: datetime | None
) -> list[HelpRow]:
    """Questions où l'enfant a demandé de l'aide, de la plus récente à la plus ancienne."""
    first = func.min(db.HelpRequest.requested_at).label("first")
    asked = (
        select(db.HelpRequest.session_item_id, first)
        .join(db.SessionItem, db.SessionItem.id == db.HelpRequest.session_item_id)
        .join(db.RevisionSession, db.RevisionSession.id == db.SessionItem.session_id)
        .where(db.RevisionSession.child_id == child_id)
        .group_by(db.HelpRequest.session_item_id)
    )
    if before is not None:
        asked = asked.having(first < before)
    found = (await session.execute(asked.order_by(first.desc()).limit(limit))).all()
    if not found:
        return []
    item_ids = [row.session_item_id for row in found]
    items = {
        item.id: (item, lesson)
        for item, lesson in await session.execute(
            select(db.SessionItem, db.Lesson)
            .join(db.RevisionSession, db.RevisionSession.id == db.SessionItem.session_id)
            .join(db.Lesson, db.Lesson.id == db.RevisionSession.lesson_id)
            .where(db.SessionItem.id.in_(item_ids))
        )
    }
    steps: dict[uuid.UUID, list[tuple[int, str, datetime]]] = defaultdict(list)
    for request in await session.scalars(
        select(db.HelpRequest)
        .where(db.HelpRequest.session_item_id.in_(item_ids))
        .order_by(db.HelpRequest.requested_at, db.HelpRequest.level)
    ):
        steps[request.session_item_id].append((request.level, request.kind, request.requested_at))
    scores = {
        item_id: float(score)
        for item_id, score in await session.execute(
            select(db.Attempt.session_item_id, db.Attempt.score).where(
                db.Attempt.session_item_id.in_(item_ids)
            )
        )
    }
    knowledge_ids = {k for item, _ in items.values() for k in item.knowledge_ids}
    knowledge = {
        row.id: (row.key, row.label)
        for row in await session.execute(
            select(db.KnowledgeItem.id, db.KnowledgeItem.key, db.KnowledgeItem.label).where(
                db.KnowledgeItem.id.in_(knowledge_ids)
            )
        )
    }
    rows = []
    for item_id, asked_at in found:
        if item_id not in items:
            continue
        item, lesson = items[item_id]
        known = [knowledge[k] for k in item.knowledge_ids if k in knowledge]
        rows.append(
            HelpRow(
                asked_at=asked_at,
                lesson_id=lesson.id,
                lesson_title=lesson.title,
                subject=lesson.subject,
                activity=BuiltActivity(
                    type=ActivityCode(item.activity_type),
                    difficulty=item.difficulty,
                    knowledge_ids=[key for key, _ in known],
                    payload=item.payload,
                    solution=item.solution,
                ),
                notions=[label for _, label in known],
                steps=steps[item_id],
                score=scores.get(item_id),
            )
        )
    return rows


@dataclass(frozen=True)
class ReportRow:
    """Une question signalée par l'enfant (🚩) : la raison, la question, sa réponse s'il en a donné."""

    id: uuid.UUID
    reported_at: datetime
    reason: str
    seen_at: datetime | None
    lesson_id: uuid.UUID
    lesson_title: str | None
    subject: str | None
    activity: BuiltActivity
    notions: list[str]
    response: dict[str, Any] | None  # None : signalée avant de répondre
    score: float | None
    # Matériel des notions de la question, pour la corriger (§5.59) : (identifiant, matériel).
    materials: list[tuple[uuid.UUID, dict[str, Any]]] = field(default_factory=list)


async def question_reports(
    session: AsyncSession, child_id: uuid.UUID, limit: int, before: datetime | None
) -> list[ReportRow]:
    """Questions signalées par l'enfant, de la plus récente à la plus ancienne."""
    query = (
        select(db.QuestionReport, db.SessionItem, db.Lesson, db.Attempt)
        .join(db.SessionItem, db.SessionItem.id == db.QuestionReport.session_item_id)
        .join(db.RevisionSession, db.RevisionSession.id == db.SessionItem.session_id)
        .join(db.Lesson, db.Lesson.id == db.RevisionSession.lesson_id)
        .outerjoin(db.Attempt, db.Attempt.session_item_id == db.SessionItem.id)
        .where(db.RevisionSession.child_id == child_id)
        .order_by(db.QuestionReport.reported_at.desc())
        .limit(limit)
    )
    if before is not None:
        query = query.where(db.QuestionReport.reported_at < before)
    found = (await session.execute(query)).all()
    ids = {k for _, item, _, _ in found for k in item.knowledge_ids}
    knowledge = {
        row.id: (row.key, row.label)
        for row in await session.execute(
            select(db.KnowledgeItem.id, db.KnowledgeItem.key, db.KnowledgeItem.label).where(
                db.KnowledgeItem.id.in_(ids)
            )
        )
    }
    materials = {
        row.knowledge_id: row.material
        for row in await session.scalars(
            select(db.KnowledgeMaterial).where(db.KnowledgeMaterial.knowledge_id.in_(ids))
        )
    }
    rows = []
    for report, item, lesson, attempt in found:
        known = [knowledge[k] for k in item.knowledge_ids if k in knowledge]
        rows.append(
            ReportRow(
                id=report.id,
                reported_at=report.reported_at,
                reason=report.reason,
                seen_at=report.seen_at,
                lesson_id=lesson.id,
                lesson_title=lesson.title,
                subject=lesson.subject,
                activity=BuiltActivity(
                    type=ActivityCode(item.activity_type),
                    difficulty=item.difficulty,
                    knowledge_ids=[key for key, _ in known],
                    payload=item.payload,
                    solution=item.solution,
                ),
                notions=[label for _, label in known],
                response=attempt.response if attempt is not None else None,
                score=float(attempt.score) if attempt is not None else None,
                materials=[(k, materials[k]) for k in item.knowledge_ids if k in materials],
            )
        )
    return rows


async def reports_to_see(session: AsyncSession, child_id: uuid.UUID) -> int:
    """Questions signalées que le parent n'a pas encore marquées comme vues."""
    count = await session.scalar(
        select(func.count(db.QuestionReport.id))
        .join(db.SessionItem, db.SessionItem.id == db.QuestionReport.session_item_id)
        .join(db.RevisionSession, db.RevisionSession.id == db.SessionItem.session_id)
        .where(db.RevisionSession.child_id == child_id, db.QuestionReport.seen_at.is_(None))
    )
    return count or 0
