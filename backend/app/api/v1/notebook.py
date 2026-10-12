"""« Mon cahier » : l'enfant relit ses leçons et ses devoirs, sans faire de jeux.

- La fiche d'une leçon : l'objectif, le résumé, chaque notion (à retenir, explication, astuce,
  carte mémoire, exemple résolu), les vidéos et exercices des sites de confiance, et le texte de
  la leçon tel qu'il a été lu. Rien de ce qui sert à noter un jeu (questions, bonnes réponses).
- Ses exercices faits avec l'aide aux devoirs, à rouvrir pour relire les étapes et la correction.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app import clock
from app.api.deps import ChildInScope, DbSession
from app.api.errors import ApiError
from app.api.v1.homework import HomeworkListOut, homework_list
from app.api.v1.lesson_content import lesson_text
from app.api.v1.lesson_resources import visible_resources
from app.api.v1.lessons import lesson_of_child
from app.api.v1.schemas_learning import LessonIllustrationOut, LessonResourceOut
from app.db.models import LessonImage
from app.domain.text import display_text
from app.services.lesson_store import load_masteries, load_units, notion_levels

router = APIRouter(tags=["enfant"])


class ExampleOut(BaseModel):
    question: str
    answer: str
    why: str | None = None


class SheetNotionOut(BaseModel):
    id: uuid.UUID
    label: str
    statement: str = Field(description="À retenir.")
    explanation: str | None = Field(None, description="L'explication, au niveau de la classe.")
    tip: str | None = Field(None, description="Une astuce pour s'en souvenir.")
    card_front: str | None = Field(None, description="Carte mémoire : la question…")
    card_back: str | None = Field(None, description="… et la réponse, à retourner.")
    example: ExampleOut | None = Field(None, description="Un exemple semblable, résolu.")
    importance: int
    level: int = Field(description="Niveau de maîtrise de l'enfant, 0 à 5.")
    image: str | None = Field(None, description="Image de la notion validée par le parent.")


class LessonSheetOut(BaseModel):
    lesson_id: uuid.UUID
    title: str | None
    subject: str | None
    grade: str | None
    objective: str | None
    summary: str | None
    text: str | None = Field(description="Le texte de la leçon, tel qu'il a été lu.")
    image: LessonIllustrationOut | None = None
    notions: list[SheetNotionOut]
    resources: list[LessonResourceOut] = Field(
        description="Vidéos, quiz et exercices des sites de confiance."
    )


def _shown(text: str | None) -> str | None:
    return display_text(text) if text else None


@router.get("/lessons/{lesson_id}/sheet")
async def lesson_sheet(lesson_id: uuid.UUID, child: ChildInScope, db: DbSession) -> LessonSheetOut:
    """La fiche de révision d'une leçon prête, à relire sans jouer."""
    lesson = await lesson_of_child(db, child, lesson_id)
    if lesson.status != "ready":
        raise ApiError(409, "lesson_not_ready", "Cette leçon n'est pas encore prête.")
    units = await load_units(db, lesson)
    levels = notion_levels(units, await load_masteries(db, child.id, units), clock.now())
    notions = []
    for unit in sorted(units.units, key=lambda u: -u.item.importance):
        material, example = unit.material, unit.material.help.example if unit.material.help else None
        notion_id = units.key_to_id[unit.id]
        notions.append(
            SheetNotionOut(
                id=notion_id,
                label=unit.item.label,
                statement=display_text(unit.item.statement),
                explanation=_shown(material.explanation),
                tip=_shown(material.tip),
                card_front=_shown(material.flashcard.front) if material.flashcard else None,
                card_back=_shown(material.flashcard.back) if material.flashcard else None,
                example=ExampleOut(
                    question=display_text(example.question),
                    answer=display_text(example.answer),
                    why=_shown(example.why),
                )
                if example
                else None,
                importance=unit.item.importance,
                level=levels[notion_id].level,
                image=unit.picture,
            )
        )
    approved = await db.scalar(
        select(LessonImage).where(
            LessonImage.lesson_id == lesson.id,
            LessonImage.knowledge_id.is_(None),
            LessonImage.status == "approved",
        )
    )
    return LessonSheetOut(
        lesson_id=lesson.id,
        title=lesson.title,
        subject=lesson.subject,
        grade=lesson.grade,
        objective=_shown(lesson.objective),
        summary=_shown(lesson.summary),
        text=await lesson_text(db, lesson) or None,
        image=LessonIllustrationOut(url=f"/v1/lessons/{lesson.id}/image", alt=approved.alt)
        if approved is not None
        else None,
        notions=notions,
        resources=await visible_resources(db, lesson.id),
    )


@router.get("/homework")
async def my_homework(
    child: ChildInScope,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    before: Annotated[
        datetime | None, Query(description="Curseur : `next_before` de la page précédente")
    ] = None,
) -> HomeworkListOut:
    """Les exercices de l'enfant faits avec l'aide aux devoirs, à rouvrir pour les relire."""
    return await homework_list(db, child.id, limit, before)
