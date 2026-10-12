"""Question ouverte : l'enfant rédige sa réponse (spécification technique §5.1, §6.4).

Niveaux de compréhension 3 (appliquer), 4 (expliquer) et 5 (transférer) : la difficulté de
l'activité vaut niveau − 2. La réponse est corrigée d'après les points clés de la question,
par l'évaluateur IA (`grade_with`) ; sans lui (panne, plafond de coût), par la présence des
mots importants de chaque point clé (`grade`), plus sévère mais jamais bloquant.
"""

import random
from dataclasses import dataclass
from typing import Any

from pydantic import Field

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
from app.domain.errors import ErrorType
from app.domain.knowledge import KnowledgeUnit
from app.domain.text import normalize

MAX_ANSWER_LENGTH = 600
LEVEL_OFFSET = 2  # difficulté 1, 2, 3 → niveau 3, 4, 5
_STOP_WORDS = {
    "les", "des", "une", "est", "sont", "dans", "pour", "par", "avec", "que", "qui", "sur",
    "plus", "moins", "aux", "ces", "son", "sa", "ses", "leur", "leurs", "elle", "il", "on",
}  # fmt: skip


class OpenQuestionResponse(ResponseModel):
    text: str = Field(max_length=MAX_ANSWER_LENGTH)


@dataclass(frozen=True)
class OpenEvaluation:
    """Correction d'une réponse rédigée (sortie validée de l'évaluateur IA)."""

    score: float  # 0 à 1
    key_points_found: list[str]
    error_type: ErrorType | None
    feedback: str
    confidence: float


def _words(text: str) -> set[str]:
    """Mots importants, réduits à leurs 6 premières lettres : « compare » et « comparer »,
    « numérateur » et « numérateurs » se rejoignent."""
    return {w[:6] for w in normalize(text).split() if len(w) > 2 and w not in _STOP_WORDS}


def point_found(answer: str, point: str) -> bool:
    """Un point clé est présent si au moins les deux tiers de ses mots importants le sont."""
    wanted = _words(point)
    if not wanted:
        return False
    return len(wanted & _words(answer)) * 3 >= len(wanted) * 2


class OpenQuestionActivity(ActivityType):
    code = ActivityCode.OPEN_QUESTION
    knowledge_types = ALL_TYPES
    difficulties = frozenset({1, 2, 3})
    base_duration_s = 60

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return bool(unit.material.open_questions)

    def _can_combine(self, units: list[KnowledgeUnit], difficulty: int) -> bool:
        return bool(units[0].material.open_questions_of(difficulty + LEVEL_OFFSET))

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        question = rng.choice(unit.material.open_questions_of(difficulty + LEVEL_OFFSET))
        payload: dict[str, Any] = {"prompt": question.prompt, "max_length": MAX_ANSWER_LENGTH}
        if question.passage:
            payload["passage"] = question.passage
        solution = {
            "key_points": question.key_points,
            "model_answer": question.model_answer,
            "display": question.model_answer,
            **feedback(unit),
        }
        return payload, solution

    def answer_text(self, response: dict[str, Any]) -> str:
        return parse_response(OpenQuestionResponse, response).text.strip()

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        text = self.answer_text(response)
        points: list[str] = activity.solution["key_points"]
        found = [p for p in points if point_found(text, p)]
        score = len(found) / len(points)
        error = (
            ErrorType.FORGOTTEN
            if not _words(text)
            else ErrorType.IMPRECISION
            if score >= 0.5
            else ErrorType.KNOWLEDGE
        )
        return self._result(activity, score, found, error, activity.solution["explanation"])

    def grade_with(
        self, activity: BuiltActivity, response: dict[str, Any], evaluation: OpenEvaluation
    ) -> Grade:
        """Correction par l'évaluateur IA ; les points clés qu'il cite doivent être ceux de la question."""
        self.answer_text(response)  # peut lever InvalidResponse
        points: list[str] = activity.solution["key_points"]
        found = [p for p in points if p in evaluation.key_points_found]
        score = min(1.0, max(0.0, evaluation.score))
        error = evaluation.error_type or ErrorType.KNOWLEDGE
        return self._result(activity, score, found, error, evaluation.feedback)

    def _result(
        self, activity: BuiltActivity, score: float, found: list[str], error: ErrorType, explanation: str
    ) -> Grade:
        knowledge_id = activity.knowledge_ids[0]
        score = round(score, 2)
        return Grade(
            score=score,
            evidence={knowledge_id: score},
            correct_answer=activity.solution["display"],
            tip=activity.solution.get("tip"),
            explanation=explanation,
            details=[{"point": p, "found": p in found} for p in activity.solution["key_points"]],
            errors={} if score >= 1 else {knowledge_id: error},
        )
