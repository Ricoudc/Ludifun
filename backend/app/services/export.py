"""Export des données d'un enfant (§16.2, droit d'accès et de portabilité) : tout ce que
Ludifun conserve sur lui, dans un seul document JSON lisible."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as db
from app.domain.understanding import notion_level
from app.services.lesson_store import load_skills, to_mastery

FORMAT_VERSION = 1


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None


async def export_child(session: AsyncSession, child: db.Child, now: datetime) -> dict[str, Any]:
    devices = await session.scalars(
        select(db.Device).where(db.Device.child_id == child.id).order_by(db.Device.created_at)
    )
    masteries = {
        m.knowledge_id: m
        for m in await session.scalars(
            select(db.KnowledgeMastery).where(db.KnowledgeMastery.child_id == child.id)
        )
    }
    lessons = []
    for lesson in await session.scalars(
        select(db.Lesson).where(db.Lesson.child_id == child.id).order_by(db.Lesson.created_at)
    ):
        pages = await session.scalars(
            select(db.LessonPage)
            .where(db.LessonPage.lesson_id == lesson.id)
            .order_by(db.LessonPage.page_index)
        )
        items = list(
            await session.scalars(
                select(db.KnowledgeItem)
                .where(db.KnowledgeItem.lesson_id == lesson.id)
                .order_by(db.KnowledgeItem.position)
            )
        )
        labels = {item.id: item.label for item in items}
        skills = (await load_skills(session, [lesson.id]))[lesson.id]
        lessons.append(
            {
                "id": str(lesson.id),
                "created_at": _iso(lesson.created_at),
                "status": lesson.status,
                "subject": lesson.subject,
                "grade": lesson.grade,
                "title": lesson.title,
                "objective": lesson.objective,
                "summary": lesson.summary,
                "text": [page.ocr_text for page in pages],  # les photos, elles, ne sont jamais gardées
                "notions": [_notion(item, masteries.get(item.id)) for item in items],
                "skills": [
                    {
                        "label": skill.label,
                        "verb": skill.verb,
                        "importance": skill.importance,
                        "notions": [labels[k] for k in skill.knowledge_ids],
                    }
                    for skill in skills
                ],
            }
        )
    return {
        "format": f"ludifun-export-v{FORMAT_VERSION}",
        "exported_at": _iso(now),
        "child": {
            "id": str(child.id),
            "display_name": child.display_name,
            "grade": child.grade,
            "avatar": child.avatar,
            "created_at": _iso(child.created_at),
            "parental_consent_at": _iso(child.parental_consent_at),
        },
        "devices": [
            {
                "name": device.name,
                "linked_at": _iso(device.created_at),
                "last_seen_at": _iso(device.last_seen_at),
                "unlinked_at": _iso(device.revoked_at),
            }
            for device in devices
        ],
        "lessons": lessons,
        "sessions": await _sessions(session, child.id),
    }


def _notion(item: db.KnowledgeItem, mastery: db.KnowledgeMastery | None) -> dict[str, Any]:
    level = notion_level(to_mastery(mastery) if mastery else None, item.required_levels)
    return {
        "label": item.label,
        "statement": item.statement,
        "importance": item.importance,
        "level": {"value": int(level.level), "label": level.label, "explanation": level.explanation},
        "mastery": None
        if mastery is None
        else {
            "score": mastery.score,
            "next_review_at": _iso(mastery.next_review_at),
            "last_practiced_at": _iso(mastery.last_practiced_at),
            "sessions": mastery.sessions_count,
            "comprehension_levels": sorted(mastery.levels),
        },
    }


async def _sessions(session: AsyncSession, child_id: uuid.UUID) -> list[dict[str, Any]]:
    out = []
    for revision in await session.scalars(
        select(db.RevisionSession)
        .where(db.RevisionSession.child_id == child_id)
        .order_by(db.RevisionSession.started_at)
    ):
        answers = await session.execute(
            select(db.SessionItem.activity_type, db.SessionItem.help_level, db.Attempt)
            .join(db.Attempt, db.Attempt.session_item_id == db.SessionItem.id)
            .where(db.SessionItem.session_id == revision.id)
            .order_by(db.Attempt.created_at)
        )
        errors: dict[uuid.UUID, list[str]] = {}
        for attempt_id, error_type in await session.execute(
            select(db.AttemptEvidence.attempt_id, db.AttemptEvidence.error_type)
            .join(db.Attempt, db.Attempt.id == db.AttemptEvidence.attempt_id)
            .join(db.SessionItem, db.SessionItem.id == db.Attempt.session_item_id)
            .where(db.SessionItem.session_id == revision.id, db.AttemptEvidence.error_type.is_not(None))
        ):
            errors.setdefault(attempt_id, []).append(error_type)
        out.append(
            {
                "id": str(revision.id),
                "lesson_id": str(revision.lesson_id),
                "kind": revision.kind,
                "status": revision.status,
                "started_at": _iso(revision.started_at),
                "completed_at": _iso(revision.completed_at),
                "score_on_10": float(revision.score_on_10) if revision.score_on_10 is not None else None,
                "answers": [
                    {
                        "activity": activity,
                        "answered_at": _iso(attempt.created_at),
                        "duration_ms": attempt.duration_ms,
                        "score": float(attempt.score),
                        "response": attempt.response,
                        "help_level": help_level,
                        "error_types": errors.get(attempt.id, []),
                    }
                    for activity, help_level, attempt in answers
                ],
            }
        )
    return out
