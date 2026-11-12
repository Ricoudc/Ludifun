"""Espace parent : relire les questions d'une leçon, en demander une nouvelle version à l'IA
(étape 25) ou les corriger soi-même (§5.59). La progression de l'enfant n'est jamais touchée :
seul le matériel change."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app import clock
from app.ai.factory import AiConfigError
from app.ai.ports import PROMPT_VERSIONS
from app.api.deps import AppSettings, CurrentParent, DbSession, Registry, get_ai_resolver
from app.api.errors import ApiError
from app.api.v1.children import own_child
from app.api.v1.lessons import ensure_ai_budget
from app.db import models as db_models
from app.domain.confidence import Confidence
from app.domain.duplicates import deduplicate
from app.domain.instructions import instruction
from app.domain.knowledge import KnowledgeItem, KnowledgeMaterial, KnowledgeUnit, LessonAnalysis, Theme
from app.domain.material_edit import Edit, EditError, Kind, editables
from app.domain.material_edit import apply_edit as apply_material_edit
from app.domain.material_view import material_blocks
from app.domain.text import clean_markup
from app.services import ai_settings
from app.services.ai_settings import AiResolver
from app.services.lesson_pipeline import LessonPipeline
from app.services.lesson_review import awaiting_parent, family_reviews
from app.services.lesson_store import load_units

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
    instruction: str | None = Field(None, description="Consigne du jeu, telle que l'enfant la lit.")


class EditableOut(BaseModel):
    """Un élément que le parent peut corriger lui-même (§5.59)."""

    kind: Kind = Field(description="question (QCM), statement (vrai ou faux), cloze, pair, flashcard.")
    index: int
    text: str = Field(description="Énoncé, affirmation, texte à trous, gauche de l'association, recto.")
    answer: str | None = Field(None, description="Bonne réponse du QCM, droite de l'association, verso.")
    distractors: list[str] = Field([], description="Les trois mauvaises réponses du QCM.")
    answers: list[str] = Field([], description="Réponses acceptées du texte à trous.")
    true: bool | None = Field(None, description="L'affirmation est vraie (true) ou fausse (false).")


class EditIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Kind
    index: int = Field(ge=0, le=200)
    before: str = Field(max_length=2000, description="Le texte avant correction, tel qu'il a été reçu.")
    text: str = Field(max_length=2000)
    answer: str | None = Field(None, max_length=500)
    distractors: list[str] = Field([], max_length=3)
    answers: list[str] = Field([], max_length=10)
    true: bool | None = None


class NotionContentOut(BaseModel):
    knowledge_id: uuid.UUID
    label: str
    statement: str
    blocks: list[BlockOut] = Field(description="Tout ce que l'enfant pourra voir, réponses comprises.")
    confidence: float | None = Field(None, description="Confiance dans la notion lue (§115), 0 à 1.")
    trust: Literal["high", "medium", "low"] | None = Field(
        None, description="medium : à vérifier ; low : pas proposée à l'enfant avant confirmation."
    )
    doubts: list[str] = Field([], description="Ce qui fait douter de la notion.")
    confirmed: bool = Field(False, description="Le parent a confirmé la notion.")
    editable: list[EditableOut] = Field([], description="Ce que le parent peut corriger lui-même.")
    removed: bool = Field(False, description="Retirée par le parent : plus proposée à l'enfant (§5.69).")


class LessonContentOut(BaseModel):
    lesson_id: uuid.UUID
    title: str | None
    grade: str = Field(description="Classe de l'enfant.")
    text: str | None = Field(None, description="Texte de la leçon tel que l'IA l'a lu.")
    notions: list[NotionContentOut]
    # Relecture par le parent (§5.69) : champs nouveaux, facultatifs pour une ancienne application.
    objective: str | None = None
    summary: str | None = None
    approved: bool = Field(True, description="Le parent a validé la leçon.")
    awaiting_parent: bool = Field(False, description="L'enfant attend que le parent la valide.")


class LessonInfoIn(BaseModel):
    """Le parent corrige le titre, l'objectif ou le résumé de la leçon (§5.69)."""

    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)
    objective: str = Field(min_length=1, max_length=400)
    summary: str = Field(min_length=1, max_length=2000)


class NotionTextIn(BaseModel):
    """Le parent corrige le nom d'une notion ou sa phrase « à retenir » (§5.69)."""

    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=120)
    statement: str = Field(min_length=1, max_length=600)


class ReworkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Reason
    comment: str | None = Field(None, max_length=500)


def notion_out(
    item: db_models.KnowledgeItem, material: db_models.KnowledgeMaterial, grade: str
) -> NotionContentOut:
    # Sans balises (« 3<sup>e</sup> ») enregistrées avant le nettoyage du matériel.
    validated = KnowledgeMaterial.model_validate(clean_markup(material.material))
    blocks = material_blocks(validated)
    confidence = Confidence(item.confidence, tuple(item.doubts)) if item.confidence is not None else None
    return NotionContentOut(
        knowledge_id=item.id,
        label=item.label,
        statement=item.statement,
        confidence=item.confidence,
        trust=confidence.trust.value if confidence else None,
        doubts=item.doubts,
        confirmed=item.confirmed_at is not None,
        removed=item.removed_at is not None,
        editable=[
            EditableOut(
                kind=e.kind,
                index=e.index,
                text=e.text,
                answer=e.answer,
                distractors=e.distractors,
                answers=e.answers,
                true=e.true,
            )
            # Les indices sont ceux du matériel enregistré (avec ses balises éventuelles).
            for e in editables(KnowledgeMaterial.model_validate(material.material))
        ],
        blocks=[
            BlockOut(
                title=b.title,
                lines=b.lines,
                instruction=instruction(b.game, grade) if b.game else None,
            )
            for b in blocks
        ],
    )


async def lesson_text(db: DbSession, lesson: db_models.Lesson) -> str:
    pages = await db.scalars(
        select(db_models.LessonPage)
        .where(db_models.LessonPage.lesson_id == lesson.id)
        .order_by(db_models.LessonPage.page_index)
    )
    return "\n\n".join(p.ocr_text for p in pages if p.ocr_text)


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
    return await content_out(db, child, lesson)


async def content_out(db: DbSession, child: db_models.Child, lesson: db_models.Lesson) -> LessonContentOut:
    """Toute la leçon pour le parent, notions retirées comprises (pour les remettre)."""
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
        text=await lesson_text(db, lesson) or None,
        notions=[notion_out(item, material, child.grade) for item, material in rows.all()],
        objective=lesson.objective,
        summary=lesson.summary,
        approved=lesson.parent_approved_at is not None,
        awaiting_parent=await awaiting_parent(db, lesson),
    )


# --------------------------------------------------------------------------- #
# Relecture par le parent avant l'enfant (§5.69)
# --------------------------------------------------------------------------- #


class ReviewSettingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class ReviewSettingOut(BaseModel):
    enabled: bool = Field(description="« Je relis chaque leçon avant mon enfant » (coché par défaut).")


async def _family_of(db: DbSession, parent: CurrentParent) -> uuid.UUID:
    family_id = await ai_settings.family_of_parent(db, parent.parent_id)
    if family_id is None:
        raise ApiError(404, "family_not_found", "Famille introuvable.")
    return family_id


@router.get("/parent/review-lessons")
async def get_review_setting(parent: CurrentParent, db: DbSession) -> ReviewSettingOut:
    return ReviewSettingOut(enabled=await family_reviews(db, await _family_of(db, parent)))


@router.put("/parent/review-lessons")
async def set_review_setting(body: ReviewSettingIn, parent: CurrentParent, db: DbSession) -> ReviewSettingOut:
    """Décocher ouvre aussitôt les leçons en attente ; cocher ne referme pas celles déjà ouvertes
    (validées avant), seulement les leçons pas encore validées."""
    family = await db.get(db_models.Family, await _family_of(db, parent))
    assert family is not None
    family.review_lessons = body.enabled
    await db.commit()
    return ReviewSettingOut(enabled=body.enabled)


@router.post("/children/{child_id}/lessons/{lesson_id}/approve")
async def approve_lesson(
    child_id: uuid.UUID, lesson_id: uuid.UUID, parent: CurrentParent, db: DbSession
) -> LessonContentOut:
    """« Valider la leçon » : l'enfant peut l'ouvrir et la réviser."""
    child = await own_child(db, parent, child_id)
    lesson = await _lesson(db, child, lesson_id)
    if not any(n.removed_at is None for n in await _notions(db, lesson)):
        raise ApiError(409, "no_notion_left", "Toutes les notions sont retirées : remettez-en au moins une.")
    lesson.parent_approved_at = lesson.parent_approved_at or clock.now()
    await db.commit()
    return await content_out(db, child, lesson)


@router.put("/children/{child_id}/lessons/{lesson_id}/info")
async def edit_lesson_info(
    child_id: uuid.UUID, lesson_id: uuid.UUID, body: LessonInfoIn, parent: CurrentParent, db: DbSession
) -> LessonContentOut:
    """Le parent corrige le titre, l'objectif et le résumé que l'enfant lira."""
    child = await own_child(db, parent, child_id)
    lesson = await _lesson(db, child, lesson_id)
    lesson.title, lesson.objective, lesson.summary = (
        body.title.strip(),
        body.objective.strip(),
        body.summary.strip(),
    )
    await db.commit()
    return await content_out(db, child, lesson)


async def _notions(db: DbSession, lesson: db_models.Lesson) -> list[db_models.KnowledgeItem]:
    return list(
        await db.scalars(
            select(db_models.KnowledgeItem).where(db_models.KnowledgeItem.lesson_id == lesson.id)
        )
    )


async def _notion(
    db: DbSession, lesson: db_models.Lesson, knowledge_id: uuid.UUID
) -> tuple[db_models.KnowledgeItem, db_models.KnowledgeMaterial]:
    row = await db.scalar(
        select(db_models.KnowledgeItem).where(
            db_models.KnowledgeItem.id == knowledge_id, db_models.KnowledgeItem.lesson_id == lesson.id
        )
    )
    material = (
        await db.get(db_models.KnowledgeMaterial, knowledge_id, with_for_update=True, populate_existing=True)
        if row
        else None
    )
    if row is None or material is None:
        raise ApiError(404, "notion_not_found", "Notion introuvable.")
    return row, material


@router.put("/children/{child_id}/lessons/{lesson_id}/notions/{knowledge_id}/text")
async def edit_notion_text(
    child_id: uuid.UUID,
    lesson_id: uuid.UUID,
    knowledge_id: uuid.UUID,
    body: NotionTextIn,
    parent: CurrentParent,
    db: DbSession,
) -> NotionContentOut:
    """Le parent corrige le nom de la notion ou sa phrase « à retenir ». Pour un mot à savoir
    écrire (§5.68), corriger le nom corrige le mot que l'enfant apprend à écrire."""
    child = await own_child(db, parent, child_id)
    lesson = await _lesson(db, child, lesson_id)
    row, material_row = await _notion(db, lesson, knowledge_id)
    label, statement = body.label.strip(), body.statement.strip()
    material = KnowledgeMaterial.model_validate(material_row.material)
    if material.spelling is not None and label != row.label:
        material = material.model_copy(
            update={"spelling": material.spelling.model_copy(update={"word": label})}
        )
        material_row.material = KnowledgeMaterial.model_validate(material.model_dump()).model_dump(
            mode="json"
        )
    row.label, row.statement = label, statement
    await db.commit()
    return notion_out(row, material_row, child.grade)


@router.post("/children/{child_id}/lessons/{lesson_id}/notions/{knowledge_id}/remove")
async def remove_notion(
    child_id: uuid.UUID, lesson_id: uuid.UUID, knowledge_id: uuid.UUID, parent: CurrentParent, db: DbSession
) -> NotionContentOut:
    """Le parent retire une notion fausse ou inventée : plus jamais proposée à l'enfant. La
    progression déjà enregistrée n'est pas effacée ; « Remettre » la rend de nouveau."""
    child = await own_child(db, parent, child_id)
    lesson = await _lesson(db, child, lesson_id)
    row, material_row = await _notion(db, lesson, knowledge_id)
    others = [n for n in await _notions(db, lesson) if n.id != row.id and n.removed_at is None]
    if not others:
        raise ApiError(
            409, "last_notion", "C'est la dernière notion de la leçon : elle ne peut pas être retirée."
        )
    row.removed_at = row.removed_at or clock.now()
    await db.commit()
    return notion_out(row, material_row, child.grade)


@router.post("/children/{child_id}/lessons/{lesson_id}/notions/{knowledge_id}/restore")
async def restore_notion(
    child_id: uuid.UUID, lesson_id: uuid.UUID, knowledge_id: uuid.UUID, parent: CurrentParent, db: DbSession
) -> NotionContentOut:
    child = await own_child(db, parent, child_id)
    lesson = await _lesson(db, child, lesson_id)
    row, material_row = await _notion(db, lesson, knowledge_id)
    row.removed_at = None
    await db.commit()
    return notion_out(row, material_row, child.grade)


@router.post("/children/{child_id}/lessons/{lesson_id}/notions/{knowledge_id}/confirm")
async def confirm_notion(
    child_id: uuid.UUID, lesson_id: uuid.UUID, knowledge_id: uuid.UUID, parent: CurrentParent, db: DbSession
) -> NotionContentOut:
    """« C'est bien ce qui est écrit » : une notion lue avec peu de confiance (§115) est confirmée
    par le parent ; elle est alors proposée à l'enfant comme les autres."""
    child = await own_child(db, parent, child_id)
    lesson = await _lesson(db, child, lesson_id)
    row = await db.scalar(
        select(db_models.KnowledgeItem).where(
            db_models.KnowledgeItem.id == knowledge_id, db_models.KnowledgeItem.lesson_id == lesson.id
        )
    )
    material = await db.get(db_models.KnowledgeMaterial, knowledge_id) if row else None
    if row is None or material is None:
        raise ApiError(404, "notion_not_found", "Notion introuvable.")
    row.confirmed_at = row.confirmed_at or clock.now()
    await db.commit()
    return notion_out(row, material, child.grade)


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

    text = await lesson_text(db, lesson)
    item = KnowledgeItem(
        id=row.key,
        type=row.type,
        label=row.label,
        statement=row.statement,
        importance=row.importance,
        attributes=row.attributes,
        source_excerpt=row.source_excerpt,
        relations=row.relations,
        theme=row.theme if row.theme in list(Theme) else None,
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
    # L'IA a pu prendre plusieurs minutes : le matériel est relu (et verrouillé) pour garder les
    # questions des sites ajoutées entre-temps en arrière-plan.
    material_row = await db.get(
        db_models.KnowledgeMaterial, knowledge_id, with_for_update=True, populate_existing=True
    )
    if material_row is None:
        raise ApiError(404, "notion_not_found", "Notion introuvable.")
    # Les questions tirées des sites de confiance (étape 29) restent ; rien de ce que l'enfant
    # voit déjà dans les autres notions de la leçon.
    sourced = [
        q
        for q in KnowledgeMaterial.model_validate(material_row.material).questions
        if q.source or q.target_error  # exercices sur une erreur qui revient (§5.74) : gardés aussi
    ]
    new = validated.material.model_copy(update={"questions": [*validated.material.questions, *sourced]})
    others = [(u.id, u.material) for u in (await load_units(db, lesson)).units if u.id != row.key]
    kept = deduplicate(
        [(row.key, new)],
        lambda _, material: bool(registry.single_options(KnowledgeUnit(item=item, material=material))),
        already=others,
    )[row.key]
    material_row.material = kept.material.model_dump(mode="json")
    material_row.rejected = [
        {"element": f"{row.key}.{r.element}", "reason": r.reason} for r in validated.rejected + kept.removed
    ]
    material_row.prompt_version = PROMPT_VERSIONS["material"]
    await db.commit()
    return notion_out(row, material_row, child.grade)


@router.put("/children/{child_id}/lessons/{lesson_id}/notions/{knowledge_id}/material")
async def edit_material(
    child_id: uuid.UUID,
    lesson_id: uuid.UUID,
    knowledge_id: uuid.UUID,
    body: EditIn,
    parent: CurrentParent,
    db: DbSession,
) -> NotionContentOut:
    """Le parent corrige lui-même une question (§5.59) : énoncé, bonne et mauvaises réponses d'un
    QCM, une affirmation, un texte à trous, une association, une carte mémoire. Le matériel
    corrigé repasse par son schéma ; la progression de l'enfant n'est pas touchée."""
    child = await own_child(db, parent, child_id)
    lesson = await _lesson(db, child, lesson_id)
    row = await db.scalar(
        select(db_models.KnowledgeItem).where(
            db_models.KnowledgeItem.id == knowledge_id, db_models.KnowledgeItem.lesson_id == lesson.id
        )
    )
    material_row = (
        await db.get(db_models.KnowledgeMaterial, knowledge_id, with_for_update=True, populate_existing=True)
        if row
        else None
    )
    if row is None or material_row is None:
        raise ApiError(404, "notion_not_found", "Notion introuvable.")
    edit = Edit(
        kind=body.kind,
        index=body.index,
        before=body.before,
        text=body.text,
        answer=body.answer,
        distractors=body.distractors,
        answers=body.answers,
        true=body.true,
    )
    try:
        corrected = apply_material_edit(KnowledgeMaterial.model_validate(material_row.material), edit)
    except EditError as exc:
        raise ApiError(422, "invalid_edit", str(exc)) from exc
    material_row.material = corrected.model_dump(mode="json")
    await db.commit()
    return notion_out(row, material_row, child.grade)
