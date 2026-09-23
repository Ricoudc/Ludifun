import random
from typing import Any, Literal

from app.domain.activities.base import (
    ActivityCode,
    ActivityType,
    BuiltActivity,
    Grade,
    ResponseModel,
    feedback,
    parse_response,
)
from app.domain.knowledge import KnowledgeType, KnowledgeUnit


class FlashcardResponse(ResponseModel):
    self_assessment: Literal["knew", "didnt_know"]


class Flashcard(ActivityType):
    """Carte mémoire : l'enfant retourne la carte puis dit s'il savait (auto-évaluation)."""

    code = ActivityCode.FLASHCARD
    knowledge_types = frozenset(
        {
            KnowledgeType.DATE,
            KnowledgeType.PERSON,
            KnowledgeType.PLACE,
            KnowledgeType.TERM,
            KnowledgeType.RULE,
            KnowledgeType.FORMULA,
        }
    )
    difficulties = frozenset({2})
    base_duration_s = 15
    evidence_factor = 0.5

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return unit.material.flashcard is not None

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        card = unit.material.flashcard
        assert card is not None
        # Le verso est dans le payload : l'enfant doit pouvoir retourner la carte.
        payload = {"front": card.front, "back": card.back}
        solution = {"display": card.back, **feedback(unit)}
        return payload, solution

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        knew = parse_response(FlashcardResponse, response).self_assessment == "knew"
        score = 1.0 if knew else 0.0
        return Grade(
            score=score,
            evidence={activity.knowledge_ids[0]: score},
            correct_answer=activity.solution["display"],
            tip=activity.solution["tip"],
            explanation=activity.solution["explanation"],
        )
