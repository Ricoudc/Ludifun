"""Memory (étape 21) : retrouver les paires (« Louis XVI » ↔ « roi de France ») en retournant
les cartes deux par deux. Le jeu continue jusqu'à la dernière paire : ce qui compte, c'est le
nombre de coups, et les paires trouvées sans se tromper."""

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
from app.domain.knowledge import KnowledgeUnit

MAX_MOVES = 60


class MemoryResponse(ResponseModel):
    moves: list[tuple[str, str]] = Field(min_length=1, max_length=MAX_MOVES)  # cartes retournées


class Memory(ActivityType):
    code = ActivityCode.MEMORY
    knowledge_types = Match.knowledge_types
    difficulties = frozenset({1})
    base_duration_s = 75
    evidence_factor = 0.5  # la chance et la mémoire des places jouent autant que la leçon
    multi_knowledge = True
    min_units = 3
    max_units = 5

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return unit.material.pair is not None

    def _can_combine(self, units: list[KnowledgeUnit], difficulty: int) -> bool:
        return Match()._can_combine(units, difficulty)

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        cards: list[tuple[str, str]] = []  # (texte, id de la notion)
        for unit in units:
            pair = unit.material.pair
            assert pair is not None
            cards += [(pair.left, unit.id), (pair.right, unit.id)]
        rng.shuffle(cards)
        # Le groupe de chaque carte est donné : l'application montre tout de suite si les deux cartes
        # retournées vont ensemble. L'effort porte sur la place des cartes et le lien entre les textes.
        groups: dict[str, str] = {}
        payload_cards, knowledge_by_card = [], {}
        for index, (text, knowledge_id) in enumerate(cards, start=1):
            card_id = f"c{index}"
            group = groups.setdefault(knowledge_id, f"p{len(groups) + 1}")
            payload_cards.append({"id": card_id, "text": text, "pair": group})
            knowledge_by_card[card_id] = knowledge_id
        pairs = {u.id: f"{u.material.pair.left} ↔ {u.material.pair.right}" for u in units if u.material.pair}
        payload = {"prompt": "Retrouve les paires qui vont ensemble.", "cards": payload_cards}
        solution = {
            "knowledge_by_card": knowledge_by_card,
            "pairs": pairs,
            "display": " ; ".join(pairs.values()),
        }
        return payload, solution

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        moves = parse_response(MemoryResponse, response).moves
        knowledge_by_card: dict[str, str] = activity.solution["knowledge_by_card"]
        found: set[str] = set()
        mistakes: dict[str, int] = dict.fromkeys(knowledge_by_card.values(), 0)
        for first, second in moves:
            if first == second or first not in knowledge_by_card or second not in knowledge_by_card:
                raise InvalidResponse("coup invalide")
            a, b = knowledge_by_card[first], knowledge_by_card[second]
            if a == b:
                found.add(a)
            else:
                for knowledge in (a, b):
                    if knowledge not in found:
                        mistakes[knowledge] += 1
        if found != set(mistakes):
            raise InvalidResponse("toutes les paires ne sont pas trouvées")
        pairs = len(mistakes)
        # Un bon joueur trouve tout en deux fois plus de coups que de paires ; au-delà, le score baisse.
        score = min(1.0, 2 * pairs / len(moves))
        evidence = {k: 1.0 if count <= 1 else 0.5 for k, count in mistakes.items()}
        return Grade(
            score=score,
            evidence=evidence,
            correct_answer=activity.solution["display"],
            details=[
                {"id": k, "correct": count <= 1, "mistakes": count, "pair": activity.solution["pairs"][k]}
                for k, count in mistakes.items()
            ],
        )
