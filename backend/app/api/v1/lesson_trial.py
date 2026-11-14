"""Espace parent : essayer la leçon avant l'enfant (§5.84).

Le parent joue la première séance que son enfant aura (mêmes jeux, mêmes consignes, même durée),
voit chaque correction et repère ce qui est faux avant de valider la leçon (§5.69).

Rien n'est enregistré : ni séance, ni réponse, ni maîtrise, ni étoiles. Le moteur est
déterministe pour une graine : la séance est recomposée à chaque correction à partir de la
graine, et une empreinte du plan dit si la leçon a changé entre-temps (question corrigée, notion
retirée) : l'essai est alors à relancer. Une réponse rédigée est corrigée par ses mots clés,
sans appel à l'IA.

« Toute la leçon » (`full`) : une séance assez longue pour que chaque notion y passe (§5.90).
Une question jugée fausse est notée (`trial_notes`) pour être corrigée ensuite.
"""

import hashlib
import json
import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app import clock
from app.api.deps import CurrentParent, DbSession, Registry
from app.api.errors import ApiError
from app.api.v1.children import own_child
from app.api.v1.lesson_content import TrialNoteOut, _lesson, note_out
from app.api.v1.schemas_learning import AttemptOut, SessionItemOut
from app.db import models as db_models
from app.domain import instructions
from app.domain.activities.base import InvalidResponse
from app.domain.composer import NothingToReview, PlannedItem, SessionComposer, SessionPlan
from app.domain.composer import _eligible as eligible
from app.domain.planning import core_size
from app.domain.simulated_pupil import respond
from app.domain.text import display_text
from app.services import learning
from app.services.lesson_store import LessonUnits, load_units

router = APIRouter(tags=["espace parent"])

OUTDATED = ApiError(409, "trial_outdated", "La leçon a changé depuis le début de l'essai : relancez-le.")


class TrialOut(BaseModel):
    """La séance d'essai : jamais les solutions, comme pour l'enfant."""

    seed: str = Field(description="Graine de la séance, à renvoyer pour chaque correction.")
    plan: str = Field(description="Empreinte de la séance, à renvoyer pour chaque correction.")
    items: list[SessionItemOut]
    notions: dict[uuid.UUID, str] = Field(description="Nom de chaque notion de la séance.")
    full: bool = Field(False, description="Séance qui passe par toutes les notions de la leçon.")
    total_notions: int | None = Field(None, description="Notions que l'enfant peut travailler dans la leçon.")
    never_shown: list[str] = Field(
        [],
        description="Notions secondaires que les séances ne travaillent pas (la leçon a assez de "
        "notions importantes) : l'enfant ne les verra pas non plus.",
    )


class TrialItemIn(BaseModel):
    seed: str = Field(pattern=r"^\d{1,19}$")
    plan: str = Field(max_length=64)
    position: int = Field(ge=1)
    full: bool = False


class TrialCheckIn(TrialItemIn):
    response: dict[str, Any]


def _fingerprint(plan: SessionPlan) -> str:
    content = [
        [i.position, i.activity.type.value, i.activity.payload, i.activity.solution] for i in plan.items
    ]
    return hashlib.sha256(json.dumps(content, sort_keys=True, default=str).encode()).hexdigest()[:32]


def _item_id(lesson_id: uuid.UUID, seed: int, position: int) -> uuid.UUID:
    return uuid.uuid5(lesson_id, f"essai:{seed}:{position}")


async def _plan(
    db: DbSession,
    child: db_models.Child,
    lesson: db_models.Lesson,
    registry: Registry,
    seed: int,
    full: bool = False,
) -> tuple[SessionPlan, LessonUnits]:
    """La première séance de l'enfant sur cette leçon : aucune maîtrise, la durée de ses réglages.
    `full` : assez d'activités pour que chaque notion y passe."""
    units = await load_units(db, lesson)
    size = core_size(child.daily_minutes)
    options = learning.SessionOptions(max(size, len(units.units)) if full else size)
    try:
        plan = learning.compose_with(SessionComposer(registry), units, {}, clock.now(), seed, options)
    except NothingToReview as exc:
        raise ApiError(409, "nothing_to_try", "Cette leçon n'a aucun exercice à essayer.") from exc
    return plan, units


@router.post("/children/{child_id}/lessons/{lesson_id}/trial")
async def start_trial(
    child_id: uuid.UUID,
    lesson_id: uuid.UUID,
    parent: CurrentParent,
    db: DbSession,
    registry: Registry,
    full: bool = False,
) -> TrialOut:
    """« Essayer la leçon » : la séance que l'enfant aura, sans rien enregistrer ; `full` : toute
    la leçon, chaque notion au moins une fois."""
    child = await own_child(db, parent, child_id)
    lesson = await _lesson(db, child, lesson_id)
    seed = learning.new_seed()
    plan, units = await _plan(db, child, lesson, registry, seed, full)
    grade = lesson.grade or child.grade
    labels = {u.id: u.item.label for u in units.units}
    items = [
        SessionItemOut(
            id=_item_id(lesson.id, seed, i.position),
            position=i.position,
            block=i.block.value,
            type=i.activity.type.value,
            difficulty=i.activity.difficulty,
            knowledge_ids=[units.key_to_id[k] for k in i.activity.knowledge_ids],
            payload=display_text(i.activity.payload),
            help_available=False,  # l'aide progressive s'essaie dans la vraie séance
            instruction=display_text(instructions.instruction(i.activity.type.value, grade)),
        )
        for i in plan.items
    ]
    used = {k for i in plan.items for k in i.activity.knowledge_ids}
    # Comme pour l'enfant : sans les notions douteuses pas encore confirmées (§115).
    proposed = [u for u in units.units if u.id not in units.doubtful] or units.units
    playable = eligible(proposed)
    return TrialOut(
        seed=str(seed),
        plan=_fingerprint(plan),
        items=items,
        notions={units.key_to_id[k]: display_text(labels[k]) for k in sorted(used)},
        full=full,
        total_notions=len(playable),
        never_shown=[display_text(u.item.label) for u in proposed if u not in playable],
    )


@router.post("/children/{child_id}/lessons/{lesson_id}/trial/check")
async def check_trial(
    child_id: uuid.UUID,
    lesson_id: uuid.UUID,
    body: TrialCheckIn,
    parent: CurrentParent,
    db: DbSession,
    registry: Registry,
) -> AttemptOut:
    """La correction d'une réponse de l'essai, telle que l'enfant la verrait. Rien n'est enregistré."""
    child = await own_child(db, parent, child_id)
    lesson = await _lesson(db, child, lesson_id)
    seed = int(body.seed)
    item, _ = await _item(db, child, lesson, registry, body)
    try:
        grade = registry.for_activity(item.activity).grade(item.activity, body.response)
    except InvalidResponse as exc:
        raise ApiError(422, "invalid_response", f"Réponse invalide : {exc}") from exc
    return AttemptOut(
        item_id=_item_id(lesson.id, seed, item.position),
        result=grade.result,
        score=grade.score,
        correct_answer=display_text(grade.correct_answer),
        tip=grade.tip and display_text(grade.tip),
        explanation=grade.explanation and display_text(grade.explanation),
        details=display_text(grade.details),
    )


async def _item(
    db: DbSession, child: db_models.Child, lesson: db_models.Lesson, registry: Registry, body: TrialItemIn
) -> tuple[PlannedItem, LessonUnits]:
    """L'activité de l'essai, recomposée ; 409 si la leçon a changé depuis le début de l'essai."""
    plan, units = await _plan(db, child, lesson, registry, int(body.seed), body.full)
    if _fingerprint(plan) != body.plan:
        raise OUTDATED
    item = next((i for i in plan.items if i.position == body.position), None)
    if item is None:
        raise ApiError(404, "item_not_found", "Activité introuvable dans cet essai.")
    return item, units


QUESTION_KEYS = ("prompt", "question", "statement", "stem", "text", "sentence", "front", "word")
QUESTION_MAX = 400


def question_text(payload: dict[str, Any], fallback: str) -> str:
    """Ce que l'activité montre, en une ligne : son énoncé s'il en a un, sinon sa consigne."""
    for key in QUESTION_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())[:QUESTION_MAX]
    return fallback


@router.post("/children/{child_id}/lessons/{lesson_id}/trial/notes")
async def note_trial_item(
    child_id: uuid.UUID,
    lesson_id: uuid.UUID,
    body: TrialItemIn,
    parent: CurrentParent,
    db: DbSession,
    registry: Registry,
) -> TrialNoteOut:
    """« Il y a une erreur dans cette question » : gardé pour être corrigé dans « Questions de la
    leçon ». La même question notée deux fois ne fait qu'une note."""
    child = await own_child(db, parent, child_id)
    lesson = await _lesson(db, child, lesson_id)
    item, units = await _item(db, child, lesson, registry, body)
    activity = item.activity
    grade = lesson.grade or child.grade
    question = question_text(
        display_text(activity.payload),
        instructions.instruction(activity.type.value, grade) or activity.type.value,
    )
    try:  # la bonne réponse, telle que la correction la montre
        answer = (
            registry.for_activity(activity).grade(activity, respond(activity, lambda _: True)).correct_answer
        )
    except (InvalidResponse, KeyError, IndexError, TypeError, ValueError, StopIteration):
        answer = None
    knowledge_id = units.key_to_id[activity.knowledge_ids[0]]
    note = await db.scalar(
        select(db_models.TrialNote).where(
            db_models.TrialNote.lesson_id == lesson.id,
            db_models.TrialNote.knowledge_id == knowledge_id,
            db_models.TrialNote.question == question,
            db_models.TrialNote.resolved_at.is_(None),
        )
    )
    if note is None:
        note = db_models.TrialNote(
            lesson_id=lesson.id,
            knowledge_id=knowledge_id,
            activity_type=activity.type.value,
            question=question,
            answer=display_text(answer) if answer else None,
        )
        db.add(note)
        await db.commit()
    return note_out(note)
