import random
from typing import Any

from app.domain.activities.base import (
    ALL_TYPES,
    ActivityCode,
    ActivityType,
    BuiltActivity,
    Grade,
    ResponseModel,
    feedback,
    parse_response,
)
from app.domain.knowledge import KnowledgeUnit


class TrueFalseResponse(ResponseModel):
    value: bool


class TrueFalse(ActivityType):
    code = ActivityCode.TRUE_FALSE
    knowledge_types = ALL_TYPES
    difficulties = frozenset({1})
    base_duration_s = 12
    evidence_factor = 0.5

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return bool(unit.material.true_statements or unit.material.false_statements)

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        material = unit.material
        options = [(s, True) for s in material.true_statements] + [
            (s, False) for s in material.false_statements
        ]
        # Autant de chances de tomber sur « vrai » que sur « faux » quand les deux existent.
        if material.true_statements and material.false_statements:
            truth = rng.random() < 0.5
            options = [o for o in options if o[1] is truth]
        statement, value = rng.choice(options)
        display = (
            "Vrai"
            if value
            else f"Faux : {material.true_statements[0] if material.true_statements else unit.item.statement}"
        )
        payload = {"statement": statement}
        solution = {"value": value, "display": display, **feedback(unit)}
        return payload, solution

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        value = parse_response(TrueFalseResponse, response).value
        score = 1.0 if value is activity.solution["value"] else 0.0
        return Grade(
            score=score,
            evidence={activity.knowledge_ids[0]: score},
            correct_answer=activity.solution["display"],
            tip=activity.solution["tip"],
            explanation=activity.solution["explanation"],
        )
