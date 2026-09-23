import random
from typing import Any

from pydantic import BaseModel, Field

from app.domain.activities.base import (
    ALL_TYPES,
    ActivityCode,
    ActivityType,
    BuiltActivity,
    Grade,
    InvalidResponse,
    ResponseModel,
    parse_response,
)
from app.domain.knowledge import KnowledgeType, KnowledgeUnit

STATEMENTS = 5
TIME_LIMIT_S = 30


class _Answer(BaseModel):
    id: str
    value: bool


class SpeedChallengeResponse(ResponseModel):
    answers: list[_Answer] = Field(max_length=STATEMENTS)
    elapsed_ms: int | None = Field(default=None, ge=0)


def _statements(unit: KnowledgeUnit) -> list[tuple[str, bool]]:
    material = unit.material
    return [(s, True) for s in material.true_statements] + [(s, False) for s in material.false_statements]


class SpeedChallenge(ActivityType):
    """Défi rapide : 5 affirmations vrai/faux en 30 secondes, sur plusieurs notions."""

    code = ActivityCode.SPEED_CHALLENGE
    knowledge_types = ALL_TYPES - {KnowledgeType.FORMULA, KnowledgeType.PROCESS}
    difficulties = frozenset({1})
    base_duration_s = 40
    evidence_factor = 0.5
    multi_knowledge = True
    min_units = 1
    max_units = STATEMENTS

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return bool(_statements(unit))

    def _can_combine(self, units: list[KnowledgeUnit], difficulty: int) -> bool:
        return (
            len({u.id for u in units}) == len(units) and sum(len(_statements(u)) for u in units) >= STATEMENTS
        )

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        pools = {u.id: _statements(u) for u in units}
        for pool in pools.values():
            rng.shuffle(pool)
        corrections = {u.id: (u.material.true_statements or [u.item.statement])[0] for u in units}

        # Tours successifs sur les notions ; à chaque tirage, on préfère la valeur
        # (vrai ou faux) la moins représentée pour obtenir un mélange équilibré.
        picked: list[tuple[str, bool, str]] = []
        order = [u.id for u in units]
        while len(picked) < STATEMENTS:
            for knowledge_id in order:
                pool = pools[knowledge_id]
                if not pool or len(picked) >= STATEMENTS:
                    continue
                trues = sum(1 for _, value, _ in picked if value)
                wanted = trues <= len(picked) - trues
                choice = next((s for s in pool if s[1] is wanted), pool[0])
                pool.remove(choice)
                picked.append((choice[0], choice[1], knowledge_id))
        rng.shuffle(picked)

        statements, answers, knowledge_by_statement, correction_by_statement = [], {}, {}, {}
        for index, (text, value, knowledge_id) in enumerate(picked, start=1):
            statement_id = f"s{index}"
            statements.append({"id": statement_id, "text": text})
            answers[statement_id] = value
            knowledge_by_statement[statement_id] = knowledge_id
            if not value:
                correction_by_statement[statement_id] = corrections[knowledge_id]
        payload = {"time_limit_s": TIME_LIMIT_S, "statements": statements}
        solution = {
            "answers": answers,
            "knowledge_by_statement": knowledge_by_statement,
            "corrections": correction_by_statement,
        }
        return payload, solution

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        parsed = parse_response(SpeedChallengeResponse, response)
        expected: dict[str, bool] = activity.solution["answers"]
        ids = [a.id for a in parsed.answers]
        if len(set(ids)) != len(ids):
            raise InvalidResponse("une affirmation a reçu deux réponses")
        if not set(ids) <= set(expected):
            raise InvalidResponse("identifiant d'affirmation inconnu")

        # Une affirmation sans réponse (temps écoulé) compte comme une erreur.
        given = {a.id: a.value for a in parsed.answers}
        per_knowledge: dict[str, list[float]] = {}
        details = []
        for statement_id, value in expected.items():
            correct = given.get(statement_id) is value
            knowledge_id = activity.solution["knowledge_by_statement"][statement_id]
            per_knowledge.setdefault(knowledge_id, []).append(1.0 if correct else 0.0)
            detail: dict[str, Any] = {"id": statement_id, "correct": correct, "expected": value}
            if not value:
                detail["correction"] = activity.solution["corrections"][statement_id]
            details.append(detail)

        good = sum(1 for d in details if d["correct"])
        return Grade(
            score=good / len(expected),
            evidence={k: sum(v) / len(v) for k, v in per_knowledge.items()},
            correct_answer=f"{good} bonne(s) réponse(s) sur {len(expected)}",
            details=details,
        )
