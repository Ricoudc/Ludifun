"""Envoie le bilan de la semaine aux parents qui l'ont demandé (§5.93), une fois par semaine.

Lancé chaque jour (`app.tools.weekly_email`) ; n'envoie que le dimanche (heure de la famille), aux
parents dont l'adresse est vérifiée, et jamais deux fois la même semaine. Le journal ne contient
ni adresse ni prénom.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import models as db
from app.domain.weekly_email import MIN_DAYS_BETWEEN, SEND_WEEKDAY, ChildWeek, body, subject
from app.services.dashboard import build_dashboard
from app.services.email import Email, EmailNotSent, EmailSender

logger = logging.getLogger("ludifun.weekly_email")
APP_HINT = "Le détail est dans l'application, sur le tableau de bord de chaque enfant."


@dataclass
class WeeklyResult:
    sent: int = 0
    failed: int = 0
    skipped_not_today: bool = False
    parents: list[str] = field(default_factory=list)  # adresses, pour --dry-run seulement


async def _children_weeks(
    session: AsyncSession, parent_id: object, now: datetime, tz: ZoneInfo
) -> list[ChildWeek]:
    families = select(db.FamilyMember.family_id).where(db.FamilyMember.parent_id == parent_id)
    children = await session.scalars(
        select(db.Child).where(db.Child.family_id.in_(families)).order_by(db.Child.created_at)
    )
    weeks = []
    for child in children:
        dashboard = await build_dashboard(session, child.id, now, 1, tz)
        weeks.append(
            ChildWeek(
                name=child.display_name,
                summary=list(dashboard.summary),
                actions=[(a.title, a.detail) for a in dashboard.week_plan],
            )
        )
    return weeks


async def send_weekly_emails(
    session: AsyncSession, settings: Settings, sender: EmailSender, now: datetime, dry_run: bool = False
) -> WeeklyResult:
    tz = ZoneInfo(settings.family_timezone)
    result = WeeklyResult()
    if now.astimezone(tz).weekday() != SEND_WEEKDAY:
        result.skipped_not_today = True
        return result
    parents = list(
        await session.scalars(
            select(db.Parent).where(
                db.Parent.weekly_email.is_(True),
                db.Parent.email_verified_at.is_not(None),
                or_(
                    db.Parent.weekly_email_sent_at.is_(None),
                    db.Parent.weekly_email_sent_at < now - timedelta(days=MIN_DAYS_BETWEEN),
                ),
            )
        )
    )
    for parent in parents:
        weeks = await _children_weeks(session, parent.id, now, tz)
        if not weeks:
            continue
        if dry_run:
            result.parents.append(parent.email)
            continue
        try:
            await sender.send(Email(parent.email, subject(weeks), body(parent.first_name, weeks, APP_HINT)))
        except EmailNotSent:
            result.failed += 1
            continue
        parent.weekly_email_sent_at = now
        await session.commit()
        result.sent += 1
    logger.info("Bilan de la semaine : %d envoyé(s), %d échec(s)", result.sent, result.failed)
    return result
