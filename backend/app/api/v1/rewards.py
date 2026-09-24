"""Progression ludique de l'enfant (étape 20) : XP, niveau, série et badges."""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from app import clock
from app.api.deps import AppSettings, ChildInScope, DbSession
from app.api.v1.schemas_rewards import BadgeOut, ProgressOut, RewardsOut, XpLineOut
from app.domain.rewards import BADGES, Badge
from app.services import rewards

router = APIRouter(tags=["enfant"])


def badge_out(badge: Badge, earned_at: datetime | None) -> BadgeOut:
    return BadgeOut(code=badge.code, emoji=badge.emoji, title=badge.title, how=badge.how, earned_at=earned_at)


def progress_out(progress: rewards.Progress) -> ProgressOut:
    earned = [badge_out(b, progress.badges[b.code]) for b in BADGES if b.code in progress.badges]
    locked = [badge_out(b, None) for b in BADGES if b.code not in progress.badges]
    return ProgressOut(
        total_xp=progress.total_xp,
        level=progress.level.level,
        level_start_xp=progress.level.start_xp,
        next_level_xp=progress.level.next_xp,
        streak_days=progress.streak.days,
        done_today=progress.streak.done_today,
        badges=earned + locked,
    )


def rewards_out(award: rewards.Award, now: datetime) -> RewardsOut:
    return RewardsOut(
        xp=sum(line.xp for line in award.xp),
        lines=[XpLineOut(label=line.label, xp=line.xp) for line in award.xp],
        message=award.message,
        new_badges=[badge_out(b, now) for b in award.new_badges],
        progress=progress_out(award.progress),
    )


@router.get("/me/progress")
async def my_progress(child: ChildInScope, db: DbSession, settings: AppSettings) -> ProgressOut:
    """XP, niveau, série et badges de l'enfant (appareil de l'enfant, ou parent avec `child_id`)."""
    return progress_out(await rewards.progress(db, child.id, clock.now(), ZoneInfo(settings.family_timezone)))
