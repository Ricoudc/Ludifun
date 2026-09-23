"""Tableau de bord et historique d'un enfant, pour l'espace parent (écrans P3 et P4).

Définitions (affichées telles quelles au parent) :
- **semaine** : du lundi 0 h au dimanche soir, à l'heure de la famille (Europe/Paris par défaut) ;
- **séances** : séances terminées dans la semaine ;
- **temps** : temps passé à répondre (chaque réponse compte au plus 5 minutes, pour ignorer une
  application laissée ouverte), plus 8 secondes par correction lue ;
- **note moyenne** : moyenne des notes sur 10 des séances terminées ;
- **réussite par matière** : maîtrise actuelle des notions travaillées (score 0-100 de §10),
  moyenne pondérée par l'importance des notions ;
- **à renforcer** : notions travaillées dont la maîtrise est sous 80 %.
"""

import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as db
from app.domain.knowledge import Subject
from app.domain.mastery import FRAGILE_RATE, MASTERED_RATE

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
        if mastery.score < 100 * MASTERED_RATE:
            weak.append(
                (
                    (mastery.score, -item.importance, mastery.next_review_at),
                    WeakNotion(
                        knowledge_id=item.id,
                        label=item.label,
                        lesson_id=lesson.id,
                        lesson_title=lesson.title,
                        subject=lesson.subject,
                        mastery=mastery.score,
                        status="to_review" if mastery.score >= 100 * FRAGILE_RATE else "not_mastered",
                        next_review_at=mastery.next_review_at,
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
    return Dashboard(
        this_week=closed[-1],
        lessons_added_this_week=lessons_added or 0,
        subjects=subjects,
        to_strengthen=[notion for _, notion in sorted(weak, key=lambda w: w[0])[:5]],
        due_now=due_now,
        weeks=closed,
        trend=trend_of(closed),
        activities=dict(activities),
    )


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
