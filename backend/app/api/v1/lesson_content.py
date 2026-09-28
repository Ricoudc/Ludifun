"""Espace parent : relire les questions d'une leçon et en demander une nouvelle version à l'IA
(étape 25). La progression de l'enfant n'est jamais touchée : seul le matériel change."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.ai.factory import AiConfigError
from app.ai.ports import PROMPT_VERSIONS
from app.api.deps import AppSettings, CurrentParent, DbSession, Registry, get_ai_resolver
from app.api.errors import ApiError
from app.api.v1.children import own_child
from app.api.v1.lessons import ensure_ai_budget
from app.db import models as db_models
from app.domain.knowledge import KnowledgeItem, KnowledgeMaterial, LessonAnalysis
from app.domain.material_view import material_blocks
from app.services.ai_settings import AiResolver
from app.services.lesson_pipeline import LessonPipeline

router = APIRouter(tags=["espace parent"])

Reason = Literal["too_hard", "too_easy", "unclear", "wrong", "other"]
REASONS: dict[str, str] = {
    "too_hard": "C'est trop difficile pour sa classe.",
    "too_easy": "C'est trop facile pour sa classe.",
    "unclear": "Les questions ou les réponses ne sont pas assez claires.",
    "wrong": "Une réponse ou une affirmation est fausse.",
    "other": "",
}


class BlockOut(BaseModel):
    title: str
    lines: list[str]


class NotionContentOut(BaseModel):
    knowledge_id: uuid.UUID
    label: str
    statement: str
    blocks: list[BlockOut] = Field(description="Tout ce que l'enfant pourra voir, réponses comprises.")


class LessonContentOut(BaseModel):
    lesson_id: uuid.UUID
    title: str | None
    grade: str = Field(description="Classe de l'enfant.")
    notions: list[NotionContentOut]


class ReworkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Reason
    comment: str | None = Field(None, max_length=500)


def notion_out(item: db_models.KnowledgeItem, material: db_models.KnowledgeMaterial) -> NotionContentOut:
    blocks = material_blocks(KnowledgeMaterial.model_validate(material.material))
    return NotionContentOut(
        knowledge_id=item.id,
        label=item.label,
        statement=item.statement,
        blocks=[BlockOut(title=b.title, lines=b.lines) for b in blocks],
    )


async def _lesson(db: DbSession, child: db_models.Child, lesson_id: uuid.UUID) -> db_models.Lesson:
    lesson = await db.scalar(
        select(db_models.Lesson).where(
            db_models.Lesson.id == lesson_id, db_models.Lesson.child_id == child.id
        )
    )
    if lesson is None or lesson.status != "ready":
        raise ApiError(404, "lesson_not_found", "Leçon introuvable.")
    return lesson


@router.get("/children/{child_id}/lessons/{lesson_id}/content")
async def get_content(
    child_id: uuid.UUID, lesson_id: uuid.UUID, parent: CurrentParent, db: DbSession
) -> LessonContentOut:
    """Toutes les questions de la leçon, notion par notion, avec leurs réponses."""
    child = await own_child(db, parent, child_id)
    lesson = await _lesson(db, child, lesson_id)
    rows = await db.execute(
        select(db_models.KnowledgeItem, db_models.KnowledgeMaterial)
        .join(
            db_models.KnowledgeMaterial,
            db_models.KnowledgeMaterial.knowledge_id == db_models.KnowledgeItem.id,
        )
        .where(db_models.KnowledgeItem.lesson_id == lesson.id)
        .order_by(db_models.KnowledgeItem.position)
    )
    return LessonContentOut(
        lesson_id=lesson.id,
        title=lesson.title,
        grade=child.grade,
        notions=[notion_out(item, material) for item, material in rows.all()],
    )


@router.post("/children/{child_id}/lessons/{lesson_id}/notions/{knowledge_id}/rework")
async def rework_notion(
    child_id: uuid.UUID,
    lesson_id: uuid.UUID,
    knowledge_id: uuid.UUID,
    body: ReworkIn,
    parent: CurrentParent,
    db: DbSession,
    settings: AppSettings,
    registry: Registry,
    resolver: Annotated[AiResolver, Depends(get_ai_resolver)],
) -> NotionContentOut:
    """Demande à l'IA une nouvelle version des questions d'une notion, d'après la remarque du
    parent. La nouvelle version passe les mêmes contrôles qu'à l'analyse ; si elle n'en passe
    aucun, l'ancienne reste (409)."""
    child = await own_child(db, parent, child_id)
    lesson = await _lesson(db, child, lesson_id)
    row = await db.scalar(
        select(db_models.KnowledgeItem).where(
            db_models.KnowledgeItem.id == knowledge_id, db_models.KnowledgeItem.lesson_id == lesson.id
        )
    )
    material_row = await db.get(db_models.KnowledgeMaterial, knowledge_id) if row else None
    if row is None or material_row is None or lesson.analysis is None:
        raise ApiError(404, "notion_not_found", "Notion introuvable.")
    remark = " ".join(part for part in (REASONS[body.reason], (body.comment or "").strip()) if part)
    if not remark:
        raise ApiError(422, "comment_required", "Dites en quelques mots ce qui ne va pas.")
    await ensure_ai_budget(db, settings)
    try:
        ocr, llm = await resolver.for_child(db, child)
    except AiConfigError as exc:
        raise ApiError(
            503, "ai_not_configured", "L'IA choisie n'est pas prête : vérifiez son réglage."
        ) from exc

    pages = await db.scalars(
        select(db_models.LessonPage)
        .where(db_models.LessonPage.lesson_id == lesson.id)
        .order_by(db_models.LessonPage.page_index)
    )
    text = "\n\n".join(p.ocr_text for p in pages)
    item = KnowledgeItem(
        id=row.key,
        type=row.type,
        label=row.label,
        statement=row.statement,
        importance=row.importance,
        attributes=row.attributes,
        source_excerpt=row.source_excerpt,
        relations=row.relations,
    )
    analysis = LessonAnalysis.model_validate(lesson.analysis)
    pipeline = LessonPipeline(ocr, llm, registry, pupil_grade=child.grade)
    validated, result = await pipeline.rework(analysis, text, item, remark)
    for run in result.runs:
        db.add(
            db_models.AiRun(
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
    if validated is None:
        await db.commit()
        raise ApiError(
            409,
            "rework_failed",
            "L'IA n'a pas proposé de meilleure version (ou elle n'a pas passé les contrôles). "
            "Les questions actuelles restent ; vous pouvez réessayer ou préciser votre remarque.",
        )
    material_row.material = validated.material.model_dump(mode="json")
    material_row.rejected = [
        {"element": f"{row.key}.{r.element}", "reason": r.reason} for r in validated.rejected
    ]
    material_row.prompt_version = PROMPT_VERSIONS["material"]
    await db.commit()
    return notion_out(row, material_row)
