"""Leçons en base : enregistrement du résultat du pipeline et rechargement pour le domaine.

Le domaine désigne les notions par leur clé dans la leçon (« k1 ») ; la base par un
UUID. `LessonUnits` fait la correspondance dans les deux sens.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as db
from app.domain.knowledge import KnowledgeItem, KnowledgeMaterial, KnowledgeUnit
from app.domain.mastery import Mastery, lesson_review
from app.services.lesson_pipeline import PipelineResult


@dataclass(frozen=True)
class LessonUnits:
    lesson: db.Lesson
    units: list[KnowledgeUnit]
    key_to_id: dict[str, uuid.UUID]

    @property
    def id_to_key(self) -> dict[uuid.UUID, str]:
        return {v: k for k, v in self.key_to_id.items()}

    @property
    def importance(self) -> dict[str, int]:
        return {u.id: u.item.importance for u in self.units}


async def save_pipeline_result(session: AsyncSession, lesson: db.Lesson, result: PipelineResult) -> None:
    """Enregistre le texte lu, l'analyse, les notions retenues, leur matériel et les appels IA."""
    await session.execute(delete(db.LessonPage).where(db.LessonPage.lesson_id == lesson.id))
    await session.execute(delete(db.KnowledgeItem).where(db.KnowledgeItem.lesson_id == lesson.id))

    if result.ocr is not None:
        for page in result.ocr.pages:
            if page.text.strip():
                session.add(
                    db.LessonPage(
                        lesson_id=lesson.id, page_index=page.index, ocr_text=page.text, quality=page.quality
                    )
                )
    for run in result.runs:
        session.add(
            db.AiRun(
                lesson_id=lesson.id,
                stage=run.stage,
                provider=run.provider,
                model=run.model,
                prompt_version=run.prompt_version,
                input_tokens=run.input_tokens,
                output_tokens=run.output_tokens,
                latency_ms=run.latency_ms,
                status=run.status,
                warnings=run.warnings[:50],
            )
        )
    lesson.prompt_versions = result.prompt_versions

    if not result.ready:
        lesson.status, lesson.failure_reason = "failed", result.failure_reason
        return

    analysis = result.analysis
    assert analysis is not None and analysis.lesson is not None
    info = analysis.lesson
    lesson.subject, lesson.grade, lesson.grade_confidence = info.subject, info.grade, info.grade_confidence
    lesson.title, lesson.objective, lesson.summary = info.title, info.objective, info.summary
    lesson.analysis = analysis.model_dump(mode="json")

    kept = {u.id: u for u in result.units}
    for position, item in enumerate(analysis.knowledge):
        unit = kept.get(item.id)
        if unit is None:
            continue  # notion sans activité possible : visible dans `analysis`, pas proposée à l'enfant
        row = db.KnowledgeItem(
            lesson_id=lesson.id,
            key=item.id,
            type=item.type,
            label=item.label,
            statement=item.statement,
            importance=item.importance,
            attributes=item.attributes,
            relations=[r.model_dump(mode="json") for r in item.relations],
            source_excerpt=item.source_excerpt,
            position=position,
        )
        session.add(row)
        await session.flush()
        rejected = [
            {"element": r.element, "reason": r.reason}
            for r in result.rejected
            if r.element.startswith(f"{item.id}.")
        ]
        session.add(
            db.KnowledgeMaterial(
                knowledge_id=row.id,
                material=unit.material.model_dump(mode="json"),
                rejected=rejected,
                prompt_version=result.prompt_versions.get("material", "?"),
            )
        )
    lesson.status, lesson.failure_reason = "ready", None


async def load_units(session: AsyncSession, lesson: db.Lesson) -> LessonUnits:
    rows = (
        await session.execute(
            select(db.KnowledgeItem, db.KnowledgeMaterial)
            .join(db.KnowledgeMaterial, db.KnowledgeMaterial.knowledge_id == db.KnowledgeItem.id)
            .where(db.KnowledgeItem.lesson_id == lesson.id)
            .order_by(db.KnowledgeItem.position)
        )
    ).all()
    units, key_to_id = [], {}
    for item, material in rows:
        domain_item = KnowledgeItem(
            id=item.key,
            type=item.type,
            label=item.label,
            statement=item.statement,
            importance=item.importance,
            attributes=item.attributes,
            source_excerpt=item.source_excerpt,
            relations=item.relations,
        )
        units.append(
            KnowledgeUnit(item=domain_item, material=KnowledgeMaterial.model_validate(material.material))
        )
        key_to_id[item.key] = item.id
    return LessonUnits(lesson, units, key_to_id)


def to_mastery(row: db.KnowledgeMastery) -> Mastery:
    return Mastery(row.score, row.box, row.next_review_at, row.last_practiced_at, row.sessions_count)


async def load_masteries(
    session: AsyncSession, child_id: uuid.UUID, lesson: LessonUnits
) -> dict[str, Mastery]:
    """Maîtrise de l'enfant pour les notions de la leçon, par clé (« k1 »)."""
    rows = await session.scalars(
        select(db.KnowledgeMastery).where(
            db.KnowledgeMastery.child_id == child_id,
            db.KnowledgeMastery.knowledge_id.in_(list(lesson.key_to_id.values())),
        )
    )
    id_to_key = lesson.id_to_key
    return {id_to_key[row.knowledge_id]: to_mastery(row) for row in rows}


async def save_masteries(
    session: AsyncSession, child_id: uuid.UUID, lesson: LessonUnits, masteries: dict[str, Mastery]
) -> None:
    ids = {lesson.key_to_id[k]: m for k, m in masteries.items()}
    existing = {
        row.knowledge_id: row
        for row in await session.scalars(
            select(db.KnowledgeMastery).where(
                db.KnowledgeMastery.child_id == child_id, db.KnowledgeMastery.knowledge_id.in_(list(ids))
            )
        )
    }
    for knowledge_id, mastery in ids.items():
        row = existing.get(knowledge_id) or db.KnowledgeMastery(child_id=child_id, knowledge_id=knowledge_id)
        row.score, row.box = mastery.score, mastery.box
        row.next_review_at, row.last_practiced_at = mastery.next_review_at, mastery.last_practiced_at
        row.sessions_count = mastery.sessions_count
        session.add(row)


@dataclass(frozen=True)
class ReviewState:
    next_review_at: datetime | None
    mastered: bool
    due: bool


def review_state(lesson: LessonUnits, masteries: dict[str, Mastery], now: datetime) -> ReviewState:
    review = lesson_review((u.item.importance, masteries.get(u.id)) for u in lesson.units)
    due = review.next_review_at is not None and review.next_review_at <= now
    return ReviewState(review.next_review_at, review.mastered, due)
