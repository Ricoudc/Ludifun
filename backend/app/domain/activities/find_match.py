"""« Trouver la correspondance » (FIND_MATCH) : toutes les réponses sont affichées ; une
définition (ou un rôle, un événement…) apparaît à la fois et l'enfant touche la réponse qui lui
correspond. Même matériel que l'association (`pair`), autre façon de jouer.
"""

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
from app.domain.activities.match import Match
from app.domain.errors import ErrorType
from app.domain.knowledge import KnowledgeUnit


class FindMatchResponse(ResponseModel):
    # [indice, réponse touchée] dans l'ordre des indices ; un indice sans réponse est raté.
    answers: list[tuple[str, str]] = Field(max_length=10)


class FindMatch(ActivityType):
    code = ActivityCode.FIND_MATCH
    knowledge_types = Match.knowledge_types
    difficulties = frozenset({2})
    base_duration_s = 50
    multi_knowledge = True
    min_units = 3
    max_units = 6

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return unit.material.pair is not None

    def _can_combine(self, units: list[KnowledgeUnit], difficulty: int) -> bool:
        return Match()._can_combine(units, difficulty)

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        pairs = [(u.id, u.material.pair) for u in units if u.material.pair is not None]
        targets = [(f"t{i}", pair.left, unit_id) for i, (unit_id, pair) in enumerate(pairs, start=1)]
        rng.shuffle(targets)
        by_unit = {unit_id: target_id for target_id, _, unit_id in targets}
        clues = [(pair.right, unit_id) for unit_id, pair in pairs]
        rng.shuffle(clues)
        expected, knowledge_by_clue, clue_list = {}, {}, []
        for i, (text, unit_id) in enumerate(clues, start=1):
            clue_id = f"c{i}"
            clue_list.append({"id": clue_id, "text": text})
            expected[clue_id] = by_unit[unit_id]
            knowledge_by_clue[clue_id] = unit_id
        target_texts = {target_id: text for target_id, text, _ in targets}
        payload = {
            "prompt": "Touche la réponse qui correspond.",
            "targets": [{"id": t, "text": text} for t, text, _ in targets],
            "clues": clue_list,
        }
        solution = {
            "expected": expected,
            "knowledge_by_clue": knowledge_by_clue,
            "target_texts": target_texts,
            "clue_texts": {c["id"]: c["text"] for c in clue_list},
            "display": " ; ".join(f"{c['text']} → {target_texts[expected[c['id']]]}" for c in clue_list),
        }
        return payload, solution

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        given = parse_response(FindMatchResponse, response).answers
        expected: dict[str, str] = activity.solution["expected"]
        clues = [clue for clue, _ in given]
        if len(set(clues)) != len(clues):
            raise InvalidResponse("un indice a reçu deux réponses")
        if not set(clues) <= set(expected) or not {t for _, t in given} <= set(expected.values()):
            raise InvalidResponse("identifiant inconnu")
        answers = dict(given)
        evidence: dict[str, float] = {}
        details = []
        for clue, target in expected.items():
            correct = answers.get(clue) == target
            evidence[activity.solution["knowledge_by_clue"][clue]] = 1.0 if correct else 0.0
            details.append(
                {
                    "id": clue,
                    "text": activity.solution.get("clue_texts", {}).get(clue, ""),
                    "correct": correct,
                    "expected": activity.solution["target_texts"][target],
                }
            )
        return Grade(
            score=sum(evidence.values()) / len(expected),
            evidence=evidence,
            errors={k: ErrorType.CONFUSION for k, result in evidence.items() if result < 1},
            correct_answer=activity.solution["display"],
            details=details,
        )
