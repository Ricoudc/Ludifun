"""Leçons de l'enfant (écrans 1 à 4) et mission du jour."""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, Request, Response, UploadFile, status
from sqlalchemy import select

from app import clock
from app.ai.images import detect_media_type, is_heic
from app.ai.ports import PageImage
from app.api.deps import Ai, AppSettings, ChildInScope, DbSession, Registry, get_database, rate_limit
from app.api.errors import ApiError
from app.api.v1.schemas_learning import (
    KnowledgeOut,
    LessonAccepted,
    LessonOut,
    LessonPatch,
    LessonSummaryOut,
    LessonTextIn,
    MissionLesson,
    MissionOut,
    ReviewIn,
    ReviewItemOut,
    SkillOut,
)
from app.db.models import Child, Lesson, LessonPage, LessonReviewItem
from app.domain.knowledge import SkillVerb
from app.domain.ocr_review import Answer, ReviewStatus, apply_answers
from app.services import ai_budget, learning
from app.services.lesson_processing import process_lesson
from app.services.lesson_store import load_masteries, load_skills, load_units, notion_levels, review_state

router = APIRouter(tags=["leçons"])

FAILURE_MESSAGES = {
    "unreadable": "Je n'arrive pas à lire ta photo. Reprends-la avec plus de lumière.",
    "not_a_lesson": "Ça ne ressemble pas à une leçon.",
    "too_long": "Cette leçon est trop longue. Photographie-la en plusieurs fois.",
    "ai_error": "Petit souci de mon côté, réessaie.",
}
STEPS = ("reading", "analyzing", "generating")
MIN_TEXT_CHARS = 40


def steps_of(lesson_status: str) -> dict[str, str] | None:
    if lesson_status == "failed":
        return None
    if lesson_status == "needs_review":
        return {"reading": "done", "analyzing": "pending", "generating": "pending"}
    if lesson_status == "ready":
        return dict.fromkeys(STEPS, "done")
    current = STEPS.index(lesson_status) if lesson_status in STEPS else -1
    return {
        step: "done" if i < current else "running" if i == current else "pending"
        for i, step in enumerate(STEPS)
    }


async def ensure_ai_budget(db: DbSession, settings: AppSettings) -> None:
    """503 tant que le plafond IA du jour est atteint (§16.1)."""
    wait = await ai_budget.seconds_until_budget(db, settings.ai_daily_budget_usd, clock.now())
    if wait is not None:
        raise ApiError(
            503,
            "ai_budget_exhausted",
            "Ludifun a analysé beaucoup de leçons aujourd'hui : réessaie demain.",
            headers={"Retry-After": str(wait)},
        )


async def lesson_of_child(db: DbSession, child: Child, lesson_id: uuid.UUID) -> Lesson:
    lesson = await db.scalar(select(Lesson).where(Lesson.id == lesson_id, Lesson.child_id == child.id))
    if lesson is None:
        raise ApiError(404, "lesson_not_found", "Leçon introuvable.")
    return lesson


async def summary_of(db: DbSession, child: Child, lesson: Lesson) -> LessonSummaryOut:
    out = LessonSummaryOut(
        id=lesson.id,
        status=lesson.status,
        failure_reason=lesson.failure_reason,
        subject=lesson.subject,
        title=lesson.title,
        created_at=lesson.created_at,
    )
    if lesson.status == "ready":
        units = await load_units(db, lesson)
        review = review_state(units, await load_masteries(db, child.id, units), clock.now())
        out.next_review_at, out.due, out.mastered = review.next_review_at, review.due, review.mastered
    return out


async def can_retry(db: DbSession, lesson: Lesson) -> bool:
    """Une analyse ratée par l'IA se relance sans reprendre la photo si le texte a été lu."""
    if lesson.status != "failed" or lesson.failure_reason != "ai_error":
        return False
    return (
        await db.scalar(select(LessonPage.page_index).where(LessonPage.lesson_id == lesson.id).limit(1))
        is not None
    )


@router.get("/lessons")
async def list_lessons(child: ChildInScope, db: DbSession) -> list[LessonSummaryOut]:
    lessons = await db.scalars(
        select(Lesson).where(Lesson.child_id == child.id).order_by(Lesson.created_at.desc()).limit(20)
    )
    return [await summary_of(db, child, lesson) for lesson in lessons]


@router.post("/lessons", status_code=status.HTTP_202_ACCEPTED)
async def create_lesson(
    request: Request,
    child: ChildInScope,
    db: DbSession,
    settings: AppSettings,
    ai: Ai,
    registry: Registry,
    background: BackgroundTasks,
    pages: Annotated[list[UploadFile], File(description="Photos de la leçon, dans l'ordre des pages")],
) -> LessonAccepted:
    """Écran 2 : les photos sont analysées en arrière-plan puis oubliées (§15)."""
    if not 1 <= len(pages) <= settings.max_pages:
        raise ApiError(422, "invalid_page_count", f"Envoie entre 1 et {settings.max_pages} photos.")
    images = []
    for upload in pages:
        data = await upload.read(settings.max_image_bytes + 1)
        if len(data) > settings.max_image_bytes:
            raise ApiError(413, "image_too_large", "Cette photo est trop lourde.")
        if is_heic(data):
            raise ApiError(415, "heic_not_supported", "Photo HEIC : l'application doit l'envoyer en JPEG.")
        media_type = detect_media_type(data)
        if media_type is None:
            raise ApiError(
                415, "unsupported_media_type", "Format de photo non pris en charge (JPEG, PNG, WebP)."
            )
        images.append(PageImage(data, media_type))
    await ensure_ai_budget(db, settings)
    rate_limit(request, f"lessons:{child.id}", limit=settings.lessons_per_day, window_s=86400)

    lesson = Lesson(child_id=child.id, status="uploaded", page_count=len(images), created_at=clock.now())
    db.add(lesson)
    await db.commit()
    background.add_task(
        process_lesson, get_database(request), ai.ocr, ai.llm, registry, settings, lesson.id, images
    )
    return LessonAccepted(id=lesson.id, status=lesson.status)


@router.post("/lessons/text", status_code=status.HTTP_202_ACCEPTED)
async def create_lesson_from_text(
    body: LessonTextIn,
    request: Request,
    child: ChildInScope,
    db: DbSession,
    settings: AppSettings,
    ai: Ai,
    registry: Registry,
    background: BackgroundTasks,
) -> LessonAccepted:
    """Leçon collée ou tapée : même analyse que pour une photo, sans l'étape de lecture."""
    text = body.text.strip()
    if len(text) < MIN_TEXT_CHARS:
        raise ApiError(422, "text_too_short", "C'est un peu court pour une leçon : colle-la en entier.")
    if len(text) > settings.max_lesson_chars:
        raise ApiError(422, "too_long", FAILURE_MESSAGES["too_long"])
    await ensure_ai_budget(db, settings)
    rate_limit(request, f"lessons:{child.id}", limit=settings.lessons_per_day, window_s=86400)
    lesson = Lesson(child_id=child.id, status="uploaded", page_count=1, source="text", created_at=clock.now())
    db.add(lesson)
    await db.commit()
    background.add_task(
        process_lesson, get_database(request), ai.ocr, ai.llm, registry, settings, lesson.id, (), text
    )
    return LessonAccepted(id=lesson.id, status=lesson.status)


async def review_items(db: DbSession, lesson: Lesson) -> list[LessonReviewItem]:
    return list(
        await db.scalars(
            select(LessonReviewItem)
            .where(LessonReviewItem.lesson_id == lesson.id)
            .order_by(LessonReviewItem.position)
        )
    )


@router.post("/lessons/{lesson_id}/review", status_code=status.HTTP_202_ACCEPTED)
async def review_lesson(
    lesson_id: uuid.UUID,
    body: ReviewIn,
    request: Request,
    child: ChildInScope,
    db: DbSession,
    settings: AppSettings,
    ai: Ai,
    registry: Registry,
    background: BackgroundTasks,
) -> LessonAccepted:
    """« Peux-tu vérifier ? » : une réponse par passage douteux, puis l'analyse reprend sur le
    texte corrigé. « Je ne sais pas » garde la lecture telle quelle."""
    lesson = await lesson_of_child(db, child, lesson_id)
    if lesson.status != "needs_review":
        raise ApiError(409, "not_awaiting_review", "Cette leçon n'attend pas de vérification.")
    items = {i.id: i for i in await review_items(db, lesson)}
    answers = {a.item_id: a for a in body.answers}
    if set(answers) != set(items):
        raise ApiError(422, "review_incomplete", "Réponds pour chaque passage à vérifier.")
    for item_id, answer in answers.items():
        correction = (answer.text or "").strip()
        if answer.status == "corrected" and not correction:
            raise ApiError(422, "review_incomplete", "Écris le bon mot, ou choisis « Je ne sais pas ».")
        item = items[item_id]
        item.status, item.answer = answer.status, correction if answer.status == "corrected" else None
    await ensure_ai_budget(db, settings)

    corrections = [
        Answer(i.page_index, i.read_text, i.context, ReviewStatus(i.status), i.answer) for i in items.values()
    ]
    pages = list(
        await db.scalars(
            select(LessonPage).where(LessonPage.lesson_id == lesson.id).order_by(LessonPage.page_index)
        )
    )
    for page in pages:
        page.ocr_text = apply_answers(page.page_index, page.ocr_text, corrections)
    text = "\n\n".join(p.ocr_text for p in pages)
    lesson.status = "uploaded"
    await db.commit()
    background.add_task(
        process_lesson, get_database(request), ai.ocr, ai.llm, registry, settings, lesson.id, (), text
    )
    return LessonAccepted(id=lesson.id, status=lesson.status)


@router.get("/lessons/{lesson_id}")
async def get_lesson(lesson_id: uuid.UUID, child: ChildInScope, db: DbSession) -> LessonOut:
    """Interrogé toutes les 1,5 s par l'écran 3, puis affiché par l'écran 4."""
    lesson = await lesson_of_child(db, child, lesson_id)
    summary = await summary_of(db, child, lesson)
    out = LessonOut(
        **summary.model_dump(),
        steps=steps_of(lesson.status),
        failure_message=FAILURE_MESSAGES.get(lesson.failure_reason or ""),
        can_retry=await can_retry(db, lesson),
        source=lesson.source,
    )
    if lesson.status == "needs_review":
        out.review = [
            ReviewItemOut(id=i.id, page_index=i.page_index, read_text=i.read_text, context=i.context)
            for i in await review_items(db, lesson)
        ]
    if lesson.status == "ready":
        units = await load_units(db, lesson)
        levels = notion_levels(units, await load_masteries(db, child.id, units))
        out.grade, out.objective, out.summary = lesson.grade, lesson.objective, lesson.summary
        out.knowledge = sorted(
            (
                KnowledgeOut(
                    id=units.key_to_id[u.id],
                    label=u.item.label,
                    statement=u.item.statement,
                    importance=u.item.importance,
                    type=u.item.type,
                    level=levels[units.key_to_id[u.id]].level,
                )
                for u in units.units
            ),
            key=lambda k: -k.importance,
        )
        out.skills = [
            SkillOut(
                id=skill.id,
                label=skill.label,
                verb=SkillVerb(skill.verb),
                importance=skill.importance,
                level=skill.level(levels),
                knowledge_ids=skill.knowledge_ids,
            )
            for skill in (await load_skills(db, [lesson.id]))[lesson.id]
        ]
    return out


@router.patch("/lessons/{lesson_id}")
async def update_lesson(
    lesson_id: uuid.UUID, body: LessonPatch, child: ChildInScope, db: DbSession
) -> LessonOut:
    """« Ce n'est pas le bon niveau ? » (écran 4)."""
    lesson = await lesson_of_child(db, child, lesson_id)
    lesson.grade = body.grade
    await db.commit()
    return await get_lesson(lesson_id, child, db)


@router.delete("/lessons/{lesson_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lesson(lesson_id: uuid.UUID, child: ChildInScope, db: DbSession) -> Response:
    await db.delete(await lesson_of_child(db, child, lesson_id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/lessons/{lesson_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_lesson(
    lesson_id: uuid.UUID,
    request: Request,
    child: ChildInScope,
    db: DbSession,
    settings: AppSettings,
    ai: Ai,
    registry: Registry,
    background: BackgroundTasks,
) -> LessonAccepted:
    lesson = await lesson_of_child(db, child, lesson_id)
    if not await can_retry(db, lesson):
        raise ApiError(409, "cannot_retry", "Cette leçon ne peut pas être relancée : reprends la photo.")
    await ensure_ai_budget(db, settings)
    pages = await db.scalars(
        select(LessonPage).where(LessonPage.lesson_id == lesson.id).order_by(LessonPage.page_index)
    )
    text = "\n\n".join(p.ocr_text for p in pages)
    lesson.status, lesson.failure_reason = "uploaded", None
    await db.commit()
    background.add_task(
        process_lesson, get_database(request), ai.ocr, ai.llm, registry, settings, lesson.id, (), text
    )
    return LessonAccepted(id=lesson.id, status=lesson.status)


@router.get("/me/mission", tags=["enfant"])
async def mission(child: ChildInScope, db: DbSession, registry: Registry) -> MissionOut:
    """Écran 1 : « 🎯 Ta mission du jour »."""
    found = await learning.mission_of_the_day(db, child.id, registry, clock.now())
    if found is None:
        return MissionOut(lesson=None)
    lesson = MissionLesson(id=found.lesson.id, title=found.lesson.title, subject=found.lesson.subject)
    return MissionOut(lesson=lesson, reason=found.reason, estimated_minutes=found.estimated_minutes)
