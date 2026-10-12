"""« Démêler » (UNJUMBLE) : les mots d'une phrase à retenir sont mélangés ; l'enfant les remet
dans l'ordre. La phrase vient de la leçon (une affirmation vraie, sinon la phrase « à retenir ») :
rien n'est demandé à l'IA. Chaque mot à sa place compte.

Un calcul a plusieurs écritures justes : « 8 + 7 = 15 » vaut « 7 + 8 = 15 » (le code calcule,
`app.domain.arithmetic`), et « la somme de 8 et 7 » vaut « la somme de 7 et 8 ». Les signes
(+, =, ×) comptent comme des mots : « 7 = 8 + 15 » est faux.

Dans une leçon de maths, seulement des calculs (« 7 + 8 = 15 ») : pas de phrase à remettre en
ordre, qui serait un exercice de français (règles 1.11.0).

Plus simple pour les petits (§5.63) : au cycle 2, les petits mots restent collés au mot qui les
suit, comme on lit (« les mammifères », « de la mer », « il mange ») ; et le nombre d'étiquettes
dépend de la classe (4 au CP, 5 au CE1… 10 au collège) : au-delà, les deux étiquettes voisines
les plus courtes sont réunies. Les phrases courtes passent d'abord au CP et au CE1. Un calcul,
ou une phrase à deux nombres (« la somme de 8 et 7 »), garde un mot par étiquette.
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
from app.domain.knowledge import Grade as SchoolGrade
from app.domain.knowledge import KnowledgeUnit, Subject
from app.domain.text import normalize

WORDS = (4, 10)  # assez de mots pour un jeu, assez peu pour un écran de téléphone
# Étiquettes à remettre dans l'ordre, au plus, selon la classe ; classe inconnue : 8.
PIECES: dict[SchoolGrade, int] = {
    SchoolGrade.CP: 4,
    SchoolGrade.CE1: 5,
    SchoolGrade.CE2: 6,
    SchoolGrade.CM1: 7,
    SchoolGrade.CM2: 8,
}
DEFAULT_PIECES = 8
YOUNG = frozenset({SchoolGrade.CP, SchoolGrade.CE1, SchoolGrade.CE2})  # cycle 2 : groupes de lecture
SHORT = {SchoolGrade.CP: 7, SchoolGrade.CE1: 8}  # mots d'une phrase préférée au CP et au CE1
# Petits mots qui se lisent avec le mot suivant (déterminants, pronoms, prépositions courtes).
_GLUE = frozenset(
    [
        "le",
        "la",
        "les",
        "un",
        "une",
        "des",
        "du",
        "de",
        "au",
        "aux",
        "a",
        "en",
        "mon",
        "ma",
        "mes",
        "ton",
        "ta",
        "tes",
        "son",
        "sa",
        "ses",
        "notre",
        "nos",
        "votre",
        "vos",
        "leur",
        "leurs",
        "ce",
        "cet",
        "cette",
        "ces",
        "je",
        "tu",
        "il",
        "elle",
        "on",
        "nous",
        "vous",
        "ils",
        "elles",
        "ne",
        "se",
        "me",
        "te",
        "y",
    ]
)


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


def _number(word: str) -> bool:
    return any(c.isdigit() for c in word)


def pieces(sentence: str, grade: SchoolGrade | None) -> list[str]:
    """Les étiquettes à remettre dans l'ordre : un mot chacune, ou des groupes pour les petits."""
    words = sentence.split()
    if _calculation(words) or sum(_number(w) for w in words) >= 2:
        return words  # « 7 + 8 = 15 », « la somme de 8 et 7 » : chaque terme compte seul
    limit = PIECES.get(grade, DEFAULT_PIECES) if grade is not None else DEFAULT_PIECES
    return reading_groups(words, glue=grade in YOUNG, limit=limit)


def reading_groups(words: list[str], *, glue: bool, limit: int) -> list[str]:
    """Les mots en groupes : les petits mots collés au mot qui les suit si `glue` (comme on lit),
    puis les deux groupes voisins les plus courts réunis tant qu'il y en a plus que `limit`.
    Sert aussi aux morceaux relus de la dictée de phrases."""
    groups: list[str] = []
    stick = False
    for word in words:
        if groups and (stick or not any(c.isalnum() for c in word)):  # « ? », « : » vont avec le mot d'avant
            groups[-1] += " " + word
        else:
            groups.append(word)
        stick = glue and (normalize(word) in _GLUE or word.endswith(("'", "’")))
    while len(groups) > limit:  # réunir les deux voisines les plus courtes
        i = min(range(len(groups) - 1), key=lambda k: len(groups[k]) + len(groups[k + 1]))
        groups[i : i + 2] = [groups[i] + " " + groups[i + 1]]
    return groups


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
        found = sentences_of(unit)
        if unit.grade in SHORT:  # au CP et au CE1, une phrase courte s'il y en a une
            found = [s for s in found if len(s.split()) <= SHORT[unit.grade]] or found
        sentence = rng.choice(found)  # une autre phrase d'une séance à l'autre
        labels = pieces(sentence, unit.grade)
        words = {f"w{i}": label for i, label in enumerate(labels, start=1)}
        order = list(words)
        # Mélange qui ne redonne jamais une écriture juste (deux mots identiques ne suffisent pas).
        for _ in range(100):
            if not accepted([words[i] for i in order], labels):
                break
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
