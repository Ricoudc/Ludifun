"""Dictée à partir d'une liste de mots (§5.99) : la leçon est enregistrée tout de suite, sans IA.

Même enregistrement qu'une leçon analysée (`save_pipeline_result`) : l'enfant la révise comme
les autres, avec les jeux d'écriture. Tapée par le parent, elle est déjà validée par lui.
"""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import OcrPage, OcrResult
from app.db import models as db
from app.domain.activities.registry import ActivityRegistry
from app.domain.knowledge import Grade, KnowledgeUnit
from app.domain.understanding import required_levels
from app.domain.word_dictation import WordEntry, dictation_lesson
from app.services.lesson_pipeline import PipelineResult
from app.services.lesson_store import save_pipeline_result

PROMPT_VERSION = "liste-de-mots"  # pas d'IA : le matériel vient du code


def _grade(value: str) -> Grade | None:
    try:
        return Grade(value)
    except ValueError:
        return None


async def create_dictation(
    session: AsyncSession,
    child: db.Child,
    entries: list[WordEntry],
    title: str | None,
    registry: ActivityRegistry,
    now: datetime,
    *,
    by_parent: bool,
) -> db.Lesson:
    built = dictation_lesson(entries, title, _grade(child.grade))
    units = [
        unit
        for item in built.analysis.knowledge
        if registry.single_options(
            unit := KnowledgeUnit(item=item, material=built.materials[item.id].material)
        )
    ]
    result = PipelineResult(
        failure_reason=None,
        ocr=OcrResult(pages=[OcrPage(index=0, quality="good", text=built.text)], language="fr", warnings=[]),
        analysis=built.analysis,
        units=units,
        required_levels={u.id: required_levels(u, registry) for u in units},
        prompt_versions={"material": PROMPT_VERSION},
    )
    lesson = db.Lesson(child_id=child.id, status="uploaded", page_count=1, source="text", created_at=now)
    session.add(lesson)
    await session.flush()
    await save_pipeline_result(session, lesson, result)
    if by_parent:
        lesson.parent_approved_at = now
    return lesson
