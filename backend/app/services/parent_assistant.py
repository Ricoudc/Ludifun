"""Assistant parent (§46) : rassembler les faits réels de l'enfant pour `app.domain.parent_assistant`.

Les mêmes données que le tableau de bord : maîtrise et oubli estimé de chaque notion, erreurs
récurrentes, temps des 7 derniers jours, objectifs et contrôles saisis par le parent.
"""

import math
import uuid
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as db
from app.domain.parent_assistant import AssistantFacts, ExamFact, NotionFact
from app.domain.understanding import MasteryLevel, notion_level
from app.services.dashboard import RECENT, build_dashboard, recent_facts
from app.services.goals import active_exams, local_day
from app.services.lesson_store import to_mastery


async def assistant_facts(
    session: AsyncSession, child: db.Child, now: datetime, tz: ZoneInfo
) -> AssistantFacts:
    rows = (
        await session.execute(
            select(db.KnowledgeItem, db.Lesson, db.KnowledgeMastery)
            .join(db.Lesson, db.Lesson.id == db.KnowledgeItem.lesson_id)
            .outerjoin(
                db.KnowledgeMastery,
                and_(
                    db.KnowledgeMastery.knowledge_id == db.KnowledgeItem.id,
                    db.KnowledgeMastery.child_id == child.id,
                ),
            )
            .where(db.Lesson.child_id == child.id, db.Lesson.status == "ready")
            .order_by(db.Lesson.created_at, db.KnowledgeItem.position)
        )
    ).all()
    notions: list[NotionFact] = []
    by_lesson: dict[uuid.UUID, list[NotionFact]] = defaultdict(list)
    recently_mastered: list[str] = []
    for item, lesson, row in rows:
        mastery = to_mastery(row) if row is not None else None
        level = notion_level(mastery, item.required_levels, now)
        fact = NotionFact(
            label=item.label,
            lesson=lesson.title,
            importance=item.importance,
            level=level.level,
            days_since=math.floor(mastery.days_since(now)) if mastery else None,
            fading=mastery.fading(now) if mastery else False,
            missing=min(level.missing) if level.missing else None,
            subject=lesson.subject,
        )
        notions.append(fact)
        by_lesson[lesson.id].append(fact)
        if mastery and level.level >= MasteryLevel.MASTERED and mastery.last_practiced_at >= now - RECENT:
            recently_mastered.append(item.label)
    recent = await recent_facts(session, child.id, now, tz)
    board = await build_dashboard(session, child.id, now, 2, tz)
    today = local_day(now, tz)
    exams = [
        ExamFact(
            title=exam.title,
            days_left=(exam.exam_date - today).days,
            notions=[n for lesson_id in exam.lesson_ids for n in by_lesson.get(lesson_id, [])],
        )
        for exam in await active_exams(session, child.id, today)
    ]
    return AssistantFacts(
        name=child.display_name,
        grade=child.grade,
        notions=notions,
        days_active=recent.days_active,
        minutes=recent.minutes,
        sessions=recent.sessions,
        daily_minutes=child.daily_minutes,
        priority_subject=child.priority_subject,
        recurring=[(r.error_type, r.label) for r in board.recurring_errors],
        exams=exams,
        week_scores=[w.average_score for w in board.weeks],
        mastered_recently=recently_mastered,
    )
