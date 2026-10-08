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
from app.domain.equivalence import any_written_match
from app.domain.errors import written_answer_error
from app.domain.knowledge import KnowledgeType, KnowledgeUnit, Subject

# Matières où l'orthographe est ce qui est appris : pas de faute tolérée, accents compris.
EXACT_SUBJECTS = frozenset({Subject.FRENCH, Subject.ENGLISH})


class FillBlankResponse(ResponseModel):
    text: str = Field(max_length=200)


class FillBlank(ActivityType):
    """Texte à trous. Accents, casse et petites fautes de frappe tolérés (§9.1), jamais sur un
    nombre ni un signe ; en français et en anglais, l'orthographe exacte (`app.domain.equivalence`).
    « 0,5 » vaut « 0.50 », « 8 + 7 » vaut « 7 + 8 », « quinze » vaut « 15 »."""

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
        solution = {
            "answers": cloze.answers,
            "display": cloze.answers[0],
            "exact_spelling": unit.subject in EXACT_SUBJECTS,
            **feedback(unit),
        }
        return payload, solution

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        given = parse_response(FillBlankResponse, response).text
        answers: list[str] = activity.solution["answers"]
        exact = bool(activity.solution.get("exact_spelling"))  # absent : activité plus ancienne
        context = str(activity.payload.get("text", ""))
        score = 1.0 if any_written_match(given, answers, exact_spelling=exact, context=context) else 0.0
        return Grade(
            score=score,
            evidence={activity.knowledge_ids[0]: score},
            errors={} if score else {activity.knowledge_ids[0]: written_answer_error(given, answers)},
            correct_answer=activity.solution["display"],
            tip=activity.solution["tip"],
            explanation=activity.solution["explanation"],
        )
