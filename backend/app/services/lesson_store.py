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
from app.domain.understanding import MasteryLevel, NotionLevel, notion_level, skill_level
from app.services.lesson_pipeline import PipelineResult


@dataclass(frozen=True)
class LessonUnits:
    lesson: db.Lesson
    units: list[KnowledgeUnit]
    key_to_id: dict[str, uuid.UUID]
    required: dict[str, frozenset[int]]  # niveaux de compréhension exigés, par notion

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
    await session.execute(delete(db.Skill).where(db.Skill.lesson_id == lesson.id))

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

    await session.execute(delete(db.LessonReviewItem).where(db.LessonReviewItem.lesson_id == lesson.id))
    if result.failure_reason is None and result.review:
        for position, uncertain in enumerate(result.review):
            session.add(
                db.LessonReviewItem(
                    lesson_id=lesson.id,
                    position=position,
                    page_index=uncertain.page_index,
                    read_text=uncertain.text,
                    context=uncertain.context,
                )
            )
        lesson.status, lesson.failure_reason = "needs_review", None
        return
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
    ids: dict[str, uuid.UUID] = {}
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
            required_levels=sorted(result.required_levels.get(item.id, {1})),
        )
        session.add(row)
        await session.flush()
        ids[item.id] = row.id
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

    # Compétences : seulement celles qui reposent sur au moins une notion proposée à l'enfant.
    for position, skill in enumerate(analysis.skills):
        linked = [ids[k] for k in skill.knowledge_ids if k in ids]
        if not linked:
            continue
        skill_row = db.Skill(
            lesson_id=lesson.id,
            key=skill.id,
            label=skill.label,
            verb=skill.verb,
            importance=skill.importance,
            source_excerpt=skill.source_excerpt,
            position=position,
        )
        session.add(skill_row)
        await session.flush()
        session.add_all(db.SkillKnowledge(skill_id=skill_row.id, knowledge_id=k) for k in linked)
    lesson.status, lesson.failure_reason = "ready", None


def picture_url(lesson_id: uuid.UUID, image_id: uuid.UUID) -> str:
    """Adresse d'une image validée, pour l'enfant (`GET /v1/lessons/{id}/images/{image_id}`)."""
    return f"/v1/lessons/{lesson_id}/images/{image_id}"


async def approved_pictures(session: AsyncSession, lesson_id: uuid.UUID) -> dict[uuid.UUID, str]:
    """Images des notions validées par le parent (étape 28) : notion → adresse."""
    rows = await session.execute(
        select(db.LessonImage.knowledge_id, db.LessonImage.id).where(
            db.LessonImage.lesson_id == lesson_id,
            db.LessonImage.knowledge_id.is_not(None),
            db.LessonImage.status == "approved",
        )
    )
    return {knowledge_id: picture_url(lesson_id, image_id) for knowledge_id, image_id in rows if knowledge_id}


async def load_units(session: AsyncSession, lesson: db.Lesson) -> LessonUnits:
    rows = (
        await session.execute(
            select(db.KnowledgeItem, db.KnowledgeMaterial)
            .join(db.KnowledgeMaterial, db.KnowledgeMaterial.knowledge_id == db.KnowledgeItem.id)
            .where(db.KnowledgeItem.lesson_id == lesson.id)
            .order_by(db.KnowledgeItem.position)
        )
    ).all()
    pictures = await approved_pictures(session, lesson.id)
    units, key_to_id, required = [], {}, {}
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
            KnowledgeUnit(
                item=domain_item,
                material=KnowledgeMaterial.model_validate(material.material),
                picture=pictures.get(item.id),
            )
        )
        key_to_id[item.key] = item.id
        required[item.key] = frozenset(item.required_levels)
    return LessonUnits(lesson, units, key_to_id, required)


@dataclass(frozen=True)
class LessonSkill:
    id: uuid.UUID
    key: str
    label: str
    verb: str
    importance: int
    knowledge_ids: list[uuid.UUID]  # dans l'ordre de la leçon

    def level(self, levels: dict[uuid.UUID, NotionLevel]) -> MasteryLevel:
        return skill_level(levels[k].level for k in self.knowledge_ids if k in levels)


async def load_skills(
    session: AsyncSession, lesson_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[LessonSkill]]:
    """Compétences des leçons, par leçon, dans l'ordre de l'analyse."""
    rows = await session.execute(
        select(db.Skill, db.SkillKnowledge.knowledge_id)
        .join(db.SkillKnowledge, db.SkillKnowledge.skill_id == db.Skill.id)
        .join(db.KnowledgeItem, db.KnowledgeItem.id == db.SkillKnowledge.knowledge_id)
        .where(db.Skill.lesson_id.in_(lesson_ids))
        .order_by(db.Skill.lesson_id, db.Skill.position, db.KnowledgeItem.position)
    )
    by_lesson: dict[uuid.UUID, list[LessonSkill]] = {lesson_id: [] for lesson_id in lesson_ids}
    skills: dict[uuid.UUID, LessonSkill] = {}
    for skill, knowledge_id in rows:
        if skill.id not in skills:
            skills[skill.id] = LessonSkill(skill.id, skill.key, skill.label, skill.verb, skill.importance, [])
            by_lesson[skill.lesson_id].append(skills[skill.id])
        skills[skill.id].knowledge_ids.append(knowledge_id)
    return by_lesson


def notion_levels(lesson: LessonUnits, masteries: dict[str, Mastery]) -> dict[uuid.UUID, NotionLevel]:
    """Niveau 0 à 5 de chaque notion de la leçon, par identifiant."""
    return {
        lesson.key_to_id[u.id]: notion_level(masteries.get(u.id), lesson.required[u.id]) for u in lesson.units
    }


def to_mastery(row: db.KnowledgeMastery) -> Mastery:
    return Mastery(
        row.score,
        row.box,
        row.next_review_at,
        row.last_practiced_at,
        row.sessions_count,
        frozenset(row.levels),
    )


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
        row.levels = sorted(mastery.levels)
        session.add(row)


@dataclass(frozen=True)
class ReviewState:
    next_review_at: datetime | None
    mastered: bool
    due: bool


def review_state(lesson: LessonUnits, masteries: dict[str, Mastery], now: datetime) -> ReviewState:
    review = lesson_review(
        (u.item.importance, masteries.get(u.id), lesson.required[u.id]) for u in lesson.units
    )
    due = review.next_review_at is not None and review.next_review_at <= now
    return ReviewState(review.next_review_at, review.mastered, due)
