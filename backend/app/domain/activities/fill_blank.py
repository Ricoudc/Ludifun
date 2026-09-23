import random
from typing import Any

from pydantic import Field

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
from app.domain.text import matches_with_typos


class FillBlankResponse(ResponseModel):
    text: str = Field(max_length=200)


class FillBlank(ActivityType):
    """Texte à trous : accents, casse et petites fautes de frappe tolérés (§9.1)."""

    code = ActivityCode.FILL_BLANK
    knowledge_types = frozenset(
        {
            KnowledgeType.DATE,
            KnowledgeType.EVENT,
            KnowledgeType.TERM,
            KnowledgeType.RULE,
            KnowledgeType.FORMULA,
            KnowledgeType.FACT,
        }
    )
    difficulties = frozenset({2})
    base_duration_s = 30

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return unit.material.cloze is not None

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        cloze = unit.material.cloze
        assert cloze is not None
        payload = {"text": cloze.text}
        solution = {"answers": cloze.answers, "display": cloze.answers[0], **feedback(unit)}
        return payload, solution

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        given = parse_response(FillBlankResponse, response).text
        answers: list[str] = activity.solution["answers"]
        score = 1.0 if any(matches_with_typos(given, a) for a in answers) else 0.0
        return Grade(
            score=score,
            evidence={activity.knowledge_ids[0]: score},
            correct_answer=activity.solution["display"],
            tip=activity.solution["tip"],
            explanation=activity.solution["explanation"],
        )
