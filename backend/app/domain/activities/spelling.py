"""Jeux d'orthographe : apprendre à écrire les mots d'une liste (dictée à préparer, mots à
savoir écrire). Le mot vient du matériel `spelling`, contrôlé : il est écrit comme dans la leçon.

- « Mot éclair » (WORD_FLASH) : le mot s'affiche quelques secondes, puis l'enfant l'écrit de
  mémoire (la « copie flash » des classes) ; plus court au niveau 3.
- « Lettres mélangées » (SCRAMBLE) : l'enfant remet les lettres du mot dans l'ordre.
- « Dictée » (DICTATION) : le téléphone lit le mot à voix haute (puis la phrase d'aide) ;
  l'enfant l'écrit sans l'avoir vu. Le mot est dans la charge utile pour être prononcé,
  l'application ne l'affiche pas.

L'orthographe est ce qui est appris : les accents comptent, pas les majuscules ni l'apostrophe
typographique.
"""

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
from app.domain.errors import written_answer_error
from app.domain.knowledge import KnowledgeType, KnowledgeUnit

ALL_TYPES = frozenset(KnowledgeType)
FLASH_MS = {2: 5000, 3: 2500}  # temps d'affichage du mot, par difficulté
SCRAMBLE_LETTERS = (3, 12)  # mots assez longs pour un jeu, assez courts pour un écran


def same_spelling(given: str, word: str) -> bool:
    def clean(text: str) -> str:
        return " ".join(text.replace("’", "'").split()).casefold()

    return clean(given) == clean(word)


def _word(unit: KnowledgeUnit) -> str:
    assert unit.material.spelling is not None
    return unit.material.spelling.word


def _sentence(unit: KnowledgeUnit) -> str | None:
    return unit.material.spelling.sentence if unit.material.spelling else None


def _written_grade(activity: BuiltActivity, given: str) -> Grade:
    word: str = activity.solution["word"]
    score = 1.0 if same_spelling(given, word) else 0.0
    knowledge = activity.knowledge_ids[0]
    return Grade(
        score=score,
        evidence={knowledge: score},
        errors={} if score else {knowledge: written_answer_error(given, [word])},
        correct_answer=word,
        tip=activity.solution["tip"],
        explanation=activity.solution["explanation"],
    )


class WordFlashResponse(ResponseModel):
    text: str = Field(max_length=100)


class WordFlash(ActivityType):
    code = ActivityCode.WORD_FLASH
    knowledge_types = ALL_TYPES
    difficulties = frozenset(FLASH_MS)
    base_duration_s = 25

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return unit.material.spelling is not None

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        payload = {
            "prompt": "Regarde bien le mot, puis écris-le sans le voir.",
            "word": _word(unit),
            "show_ms": FLASH_MS[difficulty],
            "sentence": _sentence(unit),
        }
        return payload, {"word": _word(unit), "display": _word(unit), **feedback(unit)}

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        return _written_grade(activity, parse_response(WordFlashResponse, response).text)


class Dictation(ActivityType):
    code = ActivityCode.DICTATION
    knowledge_types = ALL_TYPES
    difficulties = frozenset({3})
    base_duration_s = 30

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return unit.material.spelling is not None

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        word, sentence = _word(unit), _sentence(unit)
        payload = {
            "prompt": "Écoute le mot, puis écris-le.",
            "word": word,  # à prononcer, jamais affiché
            "sentence": sentence,
            # La phrase lue à voix haute contient le mot ; celle qui est affichée, « ___ ».
            "spoken_sentence": sentence.replace("___", word) if sentence else None,
        }
        return payload, {"word": word, "display": word, **feedback(unit)}

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        return _written_grade(activity, parse_response(WordFlashResponse, response).text)


class ScrambleResponse(ResponseModel):
    order: list[str] = Field(max_length=SCRAMBLE_LETTERS[1])


class Scramble(ActivityType):
    code = ActivityCode.SCRAMBLE
    knowledge_types = ALL_TYPES
    difficulties = frozenset({1})
    base_duration_s = 30

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        if unit.material.spelling is None:
            return False
        word = _word(unit)
        return (
            " " not in word
            and SCRAMBLE_LETTERS[0] <= len(word) <= SCRAMBLE_LETTERS[1]
            and len(set(word.casefold())) > 1
        )

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        word = _word(unit)
        letters = {f"l{i}": letter for i, letter in enumerate(word, start=1)}
        ids = list(letters)
        order = list(ids)
        while "".join(letters[i] for i in order).casefold() == word.casefold():
            rng.shuffle(order)
        payload = {
            "prompt": "Remets les lettres dans l'ordre pour écrire le mot.",
            "letters": [{"id": i, "text": letters[i]} for i in order],
            "sentence": _sentence(unit),
        }
        return payload, {"word": word, "display": word, "letters": letters, **feedback(unit)}

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        order = parse_response(ScrambleResponse, response).order
        letters: dict[str, str] = activity.solution["letters"]
        given = "".join(letters.get(i, "") for i in order)
        return _written_grade(activity, given)
