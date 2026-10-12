"""Récompenses en base (étape 20) : faits de la séance close, XP, badges, série et niveau."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as db
from app.domain.composer import Block
from app.domain.rewards import (
    SUCCESS,
    Badge,
    BadgeCode,
    PlayerLevel,
    SessionFacts,
    Streak,
    XpLine,
    cheer_text,
    earned_badges,
    encouragement,
    player_level,
    session_xp,
    streak,
)
from app.domain.understanding import MasteryLevel
from app.services.learning import CompletedSession, attempts_by_item, session_items

STRUGGLING_SCORE = 60  # maîtrise sous laquelle une notion « posait problème » avant la séance


@dataclass(frozen=True)
class Progress:
    total_xp: int
    level: PlayerLevel
    streak: Streak
    badges: dict[BadgeCode, datetime]  # gagnés, avec leur date


@dataclass(frozen=True)
class Award:
    xp: list[XpLine]
    new_badges: list[Badge]
    message: str
    progress: Progress


def _local(moment: datetime, tz: ZoneInfo) -> date:
    return moment.astimezone(tz).date()


async def _completed(session: AsyncSession, child_id: uuid.UUID) -> list[db.RevisionSession]:
    return list(
        await session.scalars(
            select(db.RevisionSession).where(
                db.RevisionSession.child_id == child_id, db.RevisionSession.status == "completed"
            )
        )
    )


async def progress(session: AsyncSession, child_id: uuid.UUID, now: datetime, tz: ZoneInfo) -> Progress:
    completed = await _completed(session, child_id)
    total = sum(s.xp_earned or 0 for s in completed)
    days = [_local(s.completed_at, tz) for s in completed if s.completed_at is not None]
    badges = {
        BadgeCode(a.code): a.earned_at
        for a in await session.scalars(select(db.Achievement).where(db.Achievement.child_id == child_id))
    }
    return Progress(total, player_level(total), streak(days, _local(now, tz)), badges)


async def _facts(
    session: AsyncSession, revision: db.RevisionSession, done: CompletedSession, now: datetime, tz: ZoneInfo
) -> SessionFacts:
    items = await session_items(session, revision)
    attempts = await attempts_by_item(session, revision)
    answered = [
        (i, attempts[i.id])
        for i in items
        if i.id in attempts and attempts[i.id].response != {"skipped": True}
    ]
    results = done.outcome.results
    previous = done.previous
    comebacks = [
        r.knowledge_id
        for r in results
        if r.knowledge_id in previous
        and previous[r.knowledge_id].score < STRUGGLING_SCORE
        and r.session_rate >= SUCCESS
    ]
    completed = await _completed(session, revision.child_id)
    today = _local(now, tz)
    today_sessions = [
        s for s in completed if s.completed_at is not None and _local(s.completed_at, tz) == today
    ]
    days = [_local(s.completed_at, tz) for s in completed if s.completed_at is not None]
    return SessionFacts(
        answered=len(answered),
        level_ups=[r.knowledge_id for r in results if r.level.level > r.previous_level.level],
        comebacks=comebacks,
        newly_mastered=[
            r.knowledge_id for r in results if r.previous_level.level < MasteryLevel.MASTERED <= r.level.level
        ],
        remediation=any(i.block == Block.REMEDIATION for i in items),
        reviewed_errors=revision.kind == "errors" or any(i.block == Block.REPLAY for i, _ in answered),
        bonus=revision.extended,
        success_after_help=any(0 < i.help_level < 5 and float(a.score) >= SUCCESS for i, a in answered),
        open_question_success=any(
            i.activity_type == "OPEN_QUESTION" and float(a.score) >= SUCCESS for i, a in answered
        ),
        lesson_mastered=done.outcome.lesson_mastered,
        first_of_day=len(today_sessions) == 1,
        streak_days=streak(days, today).days,
        sessions_completed=len(completed),
        xp_today_before=sum(s.xp_earned or 0 for s in today_sessions if s.id != revision.id),
    )


async def award(
    session: AsyncSession, revision: db.RevisionSession, done: CompletedSession, now: datetime, tz: ZoneInfo
) -> Award:
    """À la clôture (une seule fois par séance) : XP, nouveaux badges et message du bilan."""
    await session.flush()  # la séance close compte dans la série et le nombre de séances
    facts = await _facts(session, revision, done, now, tz)
    lines = session_xp(facts)
    revision.xp_earned = sum(line.xp for line in lines)
    owned = await session.scalars(
        select(db.Achievement.code).where(db.Achievement.child_id == revision.child_id)
    )
    new_badges = earned_badges(facts, owned)
    for badge in new_badges:
        session.add(
            db.Achievement(
                child_id=revision.child_id, code=badge.code.value, earned_at=now, session_id=revision.id
            )
        )
    await session.flush()
    cheer = encouragement(facts)
    labels = {u.id: u.item.label for u in done.lesson.units}
    message = cheer_text(cheer, labels.get(cheer.knowledge_id or ""), facts.streak_days)
    return Award(lines, new_badges, message, await progress(session, revision.child_id, now, tz))


async def badge_count(session: AsyncSession, child_id: uuid.UUID) -> int:
    count = await session.scalar(
        select(func.count()).select_from(db.Achievement).where(db.Achievement.child_id == child_id)
    )
    return count or 0
