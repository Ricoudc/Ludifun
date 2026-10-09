"""« Démêler » (UNJUMBLE) : les mots d'une phrase à retenir sont mélangés ; l'enfant les remet
dans l'ordre. La phrase vient de la leçon (une affirmation vraie, sinon la phrase « à retenir ») :
rien n'est demandé à l'IA. Chaque mot à sa place compte.

Un calcul a plusieurs écritures justes : « 8 + 7 = 15 » vaut « 7 + 8 = 15 » (le code calcule,
`app.domain.arithmetic`), et « la somme de 8 et 7 » vaut « la somme de 7 et 8 ». Les signes
(+, =, ×) comptent comme des mots : « 7 = 8 + 15 » est faux.

Dans une leçon de maths, seulement des calculs (« 7 + 8 = 15 ») : pas de phrase à remettre en
ordre, qui serait un exercice de français (règles 1.11.0).
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
from app.domain.arithmetic import equality_holds, swapped_terms
from app.domain.errors import ErrorType
from app.domain.knowledge import KnowledgeUnit, Subject
from app.domain.text import normalize

WORDS = (4, 10)  # assez de mots pour un jeu, assez peu pour un écran de téléphone


class UnjumbleResponse(ResponseModel):
    order: list[str] = Field(max_length=WORDS[1])


def _key(word: str) -> str:
    """Le mot comparé : sans accents ni ponctuation, mais un signe seul (+, =) reste un signe."""
    return normalize(word) or word.strip()


def accepted(placed: list[str], expected: list[str]) -> bool:
    """L'ordre donné est juste : celui de la leçon, ou une autre écriture juste du même calcul."""
    if [_key(w) for w in placed] == [_key(w) for w in expected]:
        return True
    if sorted(placed) != sorted(expected):
        return False
    return (equality_holds(expected) is True and equality_holds(placed) is True) or swapped_terms(
        placed, expected
    )


def _calculation(words: list[str]) -> bool:
    """Une égalité écrite en chiffres (« 3 × 4 = 12 ») : pas une phrase."""
    return "=" in words and all(any(c.isdigit() for c in w) or not w.isalpha() for w in words)


def sentences_of(unit: KnowledgeUnit) -> list[str]:
    """Les phrases vraies de la notion (tirées de la leçon) qui ont le bon nombre de mots."""
    found: list[str] = []
    for text in [*unit.material.true_statements, unit.item.statement]:
        words = text.split()
        if WORDS[0] <= len(words) <= WORDS[1] and len({normalize(w) for w in words}) > 1:
            if unit.subject == Subject.MATH and not _calculation(words):
                continue
            sentence = " ".join(words)
            if sentence not in found:
                found.append(sentence)
    return found


def sentence_of(unit: KnowledgeUnit) -> str | None:
    sentences = sentences_of(unit)
    return sentences[0] if sentences else None


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
        sentence = rng.choice(sentences_of(unit))  # une autre phrase d'une séance à l'autre
        words = {f"w{i}": word for i, word in enumerate(sentence.split(), start=1)}
        order = list(words)
        # Mélange qui ne redonne jamais une écriture juste (deux mots identiques ne suffisent pas).
        while accepted([words[i] for i in order], sentence.split()):
            rng.shuffle(order)
        payload = {
            "prompt": "Remets les mots dans l'ordre pour retrouver la phrase de la leçon.",
            "words": [{"id": i, "text": words[i]} for i in order],
        }
        return payload, {"sentence": sentence, "display": sentence, "words": words, **feedback(unit)}

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        given = parse_response(UnjumbleResponse, response).order
        words: dict[str, str] = activity.solution["words"]
        expected = [_key(w) for w in words.values()]
        placed = [_key(words.get(i, "")) for i in given]
        if len(given) == len(set(given)) and accepted(
            [words.get(i, "") for i in given], list(words.values())
        ):
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
