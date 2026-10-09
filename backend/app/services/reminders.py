"""Rappels du jour (§48) : la journée de chaque enfant, pour `app.domain.reminders`."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as db
from app.domain.reminders import ChildDay
from app.services.dashboard import local_midnight, recent_facts
from app.services.goals import active_exams, local_day


async def child_day(session: AsyncSession, child: db.Child, now: datetime, tz: ZoneInfo) -> ChildDay:
    today = local_day(now, tz)
    midnight = local_midnight(today, tz)
    revised = await session.scalar(
        select(db.Attempt.id)
        .join(db.SessionItem, db.SessionItem.id == db.Attempt.session_item_id)
        .join(db.RevisionSession, db.RevisionSession.id == db.SessionItem.session_id)
        .where(db.RevisionSession.child_id == child.id, db.Attempt.created_at >= midnight)
        .limit(1)
    )
    due = await session.scalars(
        select(db.KnowledgeItem.label)
        .join(db.KnowledgeMastery, db.KnowledgeMastery.knowledge_id == db.KnowledgeItem.id)
        .join(db.Lesson, db.Lesson.id == db.KnowledgeItem.lesson_id)
        .where(
            db.KnowledgeMastery.child_id == child.id,
            db.Lesson.status == "ready",
            db.KnowledgeMastery.next_review_at < midnight + timedelta(days=1),
        )
        .order_by(db.KnowledgeItem.importance.desc(), db.KnowledgeMastery.next_review_at)
    )
    exams = await active_exams(session, child.id, today)
    recent = await recent_facts(session, child.id, now, tz)
    return ChildDay(
        name=child.display_name,
        revised_today=revised is not None,
        hour=now.astimezone(tz).hour,
        due_today=list(due),
        daily_minutes=child.daily_minutes,
        days_active_last_week=recent.days_active,
        exam=(exams[0].title, (exams[0].exam_date - today).days) if exams else None,
    )
