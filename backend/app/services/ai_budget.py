"""Plafond de coût IA journalier, global (§16.1) : protège contre un emballement (boucle,
abus, bug) en refusant les nouvelles analyses une fois le budget du jour dépensé."""

import logging
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.pricing import worst_case_cost
from app.db.models import AiRun

logger = logging.getLogger("ludifun.ai_budget")


def day_start(now: datetime) -> datetime:
    return datetime.combine(now.astimezone(UTC).date(), time.min, tzinfo=UTC)


async def spent_today(db: AsyncSession, now: datetime) -> float:
    """Dépense du jour (UTC) en dollars, d'après le journal `ai_runs`."""
    rows = await db.execute(
        select(AiRun.model, func.sum(AiRun.input_tokens), func.sum(AiRun.output_tokens))
        .where(AiRun.created_at >= day_start(now))
        .group_by(AiRun.model)
    )
    return sum(worst_case_cost(model, tokens_in, tokens_out) for model, tokens_in, tokens_out in rows)


async def seconds_until_budget(db: AsyncSession, budget_usd: float | None, now: datetime) -> int | None:
    """`None` si une analyse peut partir ; sinon, secondes jusqu'au budget du lendemain."""
    if budget_usd is None:
        return None
    spent = await spent_today(db, now)
    if spent < budget_usd:
        return None
    logger.error(
        "ALERTE : plafond IA journalier atteint (%.2f $ dépensés pour %.2f $) : analyses suspendues",
        spent,
        budget_usd,
    )
    return int((day_start(now) + timedelta(days=1) - now).total_seconds()) + 1
