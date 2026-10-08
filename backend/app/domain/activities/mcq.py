import random
from typing import Any

from app.domain.activities.base import (
    ALL_TYPES,
    ActivityCode,
    ActivityType,
    BuiltActivity,
    Grade,
    InvalidResponse,
    ResponseModel,
    feedback,
    parse_response,
)
from app.domain.errors import ErrorType
from app.domain.knowledge import KnowledgeUnit

CHOICE_IDS = ("a", "b", "c", "d")


class McqResponse(ResponseModel):
    choice_id: str


class Mcq(ActivityType):
    """QCM à 4 choix. Difficulté 1 : reconnaître ; 2 : « QCM inversé » ; 3 : relier."""

    code = ActivityCode.MCQ
    knowledge_types = ALL_TYPES
    difficulties = frozenset({1, 2, 3})
    base_duration_s = 20

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return bool(unit.material.questions)

    def _can_combine(self, units: list[KnowledgeUnit], difficulty: int) -> bool:
        return bool(units[0].material.questions_of(difficulty))

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        question = rng.choice(unit.material.questions_of(difficulty))
        texts = [question.answer, *question.distractors]
        rng.shuffle(texts)
        choices = [{"id": cid, "text": text} for cid, text in zip(CHOICE_IDS, texts, strict=True)]
        answer_id = CHOICE_IDS[texts.index(question.answer)]
        misconceptions = {
            cid: kind
            for cid, text in zip(CHOICE_IDS, texts, strict=True)
            if text != question.answer and (kind := question.misconception_of(text)) is not None
        }
        payload: dict[str, Any] = {"prompt": question.stem, "choices": choices}
        if question.passage:
            payload["passage"] = question.passage  # à relire : l'enfant n'a plus la fiche
        solution = {
            "choice_id": answer_id,
            "display": question.answer,
            "misconceptions": misconceptions,
            **feedback(unit),
        }
        if question.source is not None:
            # Question d'un site de confiance (§117) : l'enfant sait d'où elle vient, et la
            # correction cite la phrase qui prouve la réponse.
            payload["source"] = question.source.site
            solution["explanation"] = f"D'après {question.source.site} : « {question.source.quote} »"
        return payload, solution

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        choice = parse_response(McqResponse, response).choice_id
        if choice not in CHOICE_IDS:
            raise InvalidResponse(f"choix inconnu : {choice}")
        score = 1.0 if choice == activity.solution["choice_id"] else 0.0
        knowledge_id = activity.knowledge_ids[0]
        # Le distracteur choisi dit quelle erreur a été faite (séances antérieures : inconnue).
        kind = activity.solution.get("misconceptions", {}).get(choice)
        error = ErrorType(kind) if kind in ErrorType else ErrorType.KNOWLEDGE
        return Grade(
            score=score,
            evidence={knowledge_id: score},
            errors={} if score else {knowledge_id: error},
            correct_answer=activity.solution["display"],
            tip=activity.solution["tip"],
            explanation=activity.solution["explanation"],
        )
