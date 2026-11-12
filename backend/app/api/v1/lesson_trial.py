"""Espace parent : essayer la leçon avant l'enfant (§5.84).

Le parent joue la première séance que son enfant aura (mêmes jeux, mêmes consignes, même durée),
voit chaque correction et repère ce qui est faux avant de valider la leçon (§5.69).

Rien n'est enregistré : ni séance, ni réponse, ni maîtrise, ni étoiles. Le moteur est
déterministe pour une graine : la séance est recomposée à chaque correction à partir de la
graine, et une empreinte du plan dit si la leçon a changé entre-temps (question corrigée, notion
retirée) : l'essai est alors à relancer. Une réponse rédigée est corrigée par ses mots clés,
sans appel à l'IA.
"""

import hashlib
import json
import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import clock
from app.api.deps import CurrentParent, DbSession, Registry
from app.api.errors import ApiError
from app.api.v1.children import own_child
from app.api.v1.lesson_content import _lesson
from app.api.v1.schemas_learning import AttemptOut, SessionItemOut
from app.db import models as db_models
from app.domain import instructions
from app.domain.activities.base import InvalidResponse
from app.domain.composer import NothingToReview, SessionComposer, SessionPlan
from app.domain.planning import core_size
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


class TrialCheckIn(BaseModel):
    seed: str = Field(pattern=r"^\d{1,19}$")
    plan: str = Field(max_length=64)
    position: int = Field(ge=1)
    response: dict[str, Any]


def _fingerprint(plan: SessionPlan) -> str:
    content = [
        [i.position, i.activity.type.value, i.activity.payload, i.activity.solution] for i in plan.items
    ]
    return hashlib.sha256(json.dumps(content, sort_keys=True, default=str).encode()).hexdigest()[:32]


def _item_id(lesson_id: uuid.UUID, seed: int, position: int) -> uuid.UUID:
    return uuid.uuid5(lesson_id, f"essai:{seed}:{position}")


async def _plan(
    db: DbSession, child: db_models.Child, lesson: db_models.Lesson, registry: Registry, seed: int
) -> tuple[SessionPlan, LessonUnits]:
    """La première séance de l'enfant sur cette leçon : aucune maîtrise, la durée de ses réglages."""
    units = await load_units(db, lesson)
    options = learning.SessionOptions(core_size(child.daily_minutes))
    try:
        plan = learning.compose_with(SessionComposer(registry), units, {}, clock.now(), seed, options)
    except NothingToReview as exc:
        raise ApiError(409, "nothing_to_try", "Cette leçon n'a aucun exercice à essayer.") from exc
    return plan, units


@router.post("/children/{child_id}/lessons/{lesson_id}/trial")
async def start_trial(
    child_id: uuid.UUID, lesson_id: uuid.UUID, parent: CurrentParent, db: DbSession, registry: Registry
) -> TrialOut:
    """« Essayer la leçon » : la séance que l'enfant aura, sans rien enregistrer."""
    child = await own_child(db, parent, child_id)
    lesson = await _lesson(db, child, lesson_id)
    seed = learning.new_seed()
    plan, units = await _plan(db, child, lesson, registry, seed)
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
    return TrialOut(
        seed=str(seed),
        plan=_fingerprint(plan),
        items=items,
        notions={units.key_to_id[k]: display_text(labels[k]) for k in sorted(used)},
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
    plan, _ = await _plan(db, child, lesson, registry, seed)
    if _fingerprint(plan) != body.plan:
        raise OUTDATED
    item = next((i for i in plan.items if i.position == body.position), None)
    if item is None:
        raise ApiError(404, "item_not_found", "Activité introuvable dans cet essai.")
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
