import random
from typing import Any

from pydantic import Field

from app.domain.activities.base import (
    ActivityCode,
    ActivityType,
    BuiltActivity,
    Grade,
    InvalidResponse,
    ResponseModel,
    parse_response,
)
from app.domain.errors import ErrorType
from app.domain.knowledge import KnowledgeType, KnowledgeUnit
from app.domain.text import normalize


class MatchResponse(ResponseModel):
    pairs: list[tuple[str, str]] = Field(max_length=10)


class Match(ActivityType):
    """Association : relier chaque élément de gauche à son élément de droite."""

    code = ActivityCode.MATCH
    knowledge_types = frozenset(
        {
            KnowledgeType.DATE,
            KnowledgeType.PERSON,
            KnowledgeType.PLACE,
            KnowledgeType.EVENT,
            KnowledgeType.TERM,
            KnowledgeType.FORMULA,
            KnowledgeType.CLASSIFICATION,
        }
    )
    difficulties = frozenset({2})
    base_duration_s = 60
    multi_knowledge = True
    min_units = 3  # le composeur vise 4 à 5 paires ; 3 permet l'association sur les petites leçons
    max_units = 5

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return unit.material.pair is not None

    def _can_combine(self, units: list[KnowledgeUnit], difficulty: int) -> bool:
        pairs = [u.material.pair for u in units if u.material.pair is not None]
        lefts = {normalize(p.left) for p in pairs}
        rights = {normalize(p.right) for p in pairs}
        # Deux éléments identiques rendraient l'association ambiguë.
        return len({u.id for u in units}) == len(units) == len(lefts) == len(rights)

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        shuffled_units = list(units)
        rng.shuffle(shuffled_units)
        left, pairs, knowledge_by_left, display = [], {}, {}, []
        rights: list[tuple[str, str]] = []  # (texte, id de gauche correspondant)
        for index, unit in enumerate(shuffled_units, start=1):
            pair = unit.material.pair
            assert pair is not None
            left_id = f"l{index}"
            left.append({"id": left_id, "text": pair.left})
            knowledge_by_left[left_id] = unit.id
            rights.append((pair.right, left_id))
            display.append(f"{pair.left} → {pair.right}")
        rng.shuffle(rights)
        right = []
        for index, (text, left_id) in enumerate(rights, start=1):
            right_id = f"r{index}"
            right.append({"id": right_id, "text": text})
            pairs[left_id] = right_id
        payload = {"left": left, "right": right}
        solution = {
            "pairs": pairs,
            "knowledge_by_left": knowledge_by_left,
            "right_texts": {r["id"]: r["text"] for r in right},
            "display": " ; ".join(display),
        }
        return payload, solution

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        given = parse_response(MatchResponse, response).pairs
        expected: dict[str, str] = activity.solution["pairs"]
        lefts = [left for left, _ in given]
        rights = [right for _, right in given]
        if len(set(lefts)) != len(lefts) or len(set(rights)) != len(rights):
            raise InvalidResponse("un élément est associé deux fois")
        if not set(lefts) <= set(expected) or not set(rights) <= set(expected.values()):
            raise InvalidResponse("identifiant d'élément inconnu")

        answers = dict(given)
        evidence: dict[str, float] = {}
        details = []
        for left_id, right_id in expected.items():
            correct = answers.get(left_id) == right_id
            evidence[activity.solution["knowledge_by_left"][left_id]] = 1.0 if correct else 0.0
            details.append(
                {"id": left_id, "correct": correct, "expected": activity.solution["right_texts"][right_id]}
            )
        return Grade(
            score=sum(evidence.values()) / len(expected),
            evidence=evidence,
            errors={k: ErrorType.CONFUSION for k, result in evidence.items() if result < 1},
            correct_answer=activity.solution["display"],
            details=details,
        )
