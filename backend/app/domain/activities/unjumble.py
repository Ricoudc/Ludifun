"""« Démêler » (UNJUMBLE) : les mots d'une phrase à retenir sont mélangés ; l'enfant les remet
dans l'ordre. La phrase vient de la leçon (une affirmation vraie, sinon la phrase « à retenir ») :
rien n'est demandé à l'IA. Chaque mot à sa place compte.
"""

import random
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

WORDS = (4, 10)  # assez de mots pour un jeu, assez peu pour un écran de téléphone


class UnjumbleResponse(ResponseModel):
    order: list[str] = Field(max_length=WORDS[1])


def sentence_of(unit: KnowledgeUnit) -> str | None:
    """La première phrase de la notion qui a le bon nombre de mots (vraie, tirée de la leçon)."""
    for text in [*unit.material.true_statements, unit.item.statement]:
        words = text.split()
        if WORDS[0] <= len(words) <= WORDS[1] and len({normalize(w) for w in words}) > 1:
            return " ".join(words)
    return None


class Unjumble(ActivityType):
    code = ActivityCode.UNJUMBLE
    knowledge_types = ALL_TYPES
    difficulties = frozenset({2})
    base_duration_s = 30  # comme les lettres mélangées

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return sentence_of(unit) is not None

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        sentence = sentence_of(unit)
        assert sentence is not None
        words = {f"w{i}": word for i, word in enumerate(sentence.split(), start=1)}
        order = list(words)
        # Mélange qui ne redonne jamais la phrase (deux mots identiques ne suffisent pas).
        while normalize(" ".join(words[i] for i in order)) == normalize(sentence):
            rng.shuffle(order)
        payload = {
            "prompt": "Remets les mots dans l'ordre pour retrouver la phrase de la leçon.",
            "words": [{"id": i, "text": words[i]} for i in order],
        }
        return payload, {"sentence": sentence, "display": sentence, "words": words, **feedback(unit)}

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        given = parse_response(UnjumbleResponse, response).order
        words: dict[str, str] = activity.solution["words"]
        expected = [normalize(w) for w in words.values()]
        placed = [normalize(words.get(i, "")) for i in given]
        if placed == expected:
            score = 1.0
        else:
            # Un mot répété (« la … la ») compte juste quelle que soit l'étiquette posée.
            score = sum(1 for a, b in zip(placed, expected, strict=False) if a == b) / len(expected)
            score = min(score, 0.9)
        knowledge = activity.knowledge_ids[0]
        return Grade(
            score=score,
            evidence={knowledge: score},
            errors={} if score >= 1 else {knowledge: ErrorType.KNOWLEDGE},
            correct_answer=activity.solution["sentence"],
            tip=activity.solution["tip"],
            explanation=activity.solution["explanation"],
        )
