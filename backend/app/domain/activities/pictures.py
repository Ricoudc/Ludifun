"""Apprendre par l'image (étape 28) : chaque notion concrète peut avoir une image qui la montre
(un volcan, une chenille, un château fort…), dessinée sur le PC et **validée par le parent**.

- « Image et mot » (`PICTURE_MATCH`) : relier chaque image au mot de la leçon qu'elle montre.
- « Quelle image ? » (`PICTURE_FIND`) : la phrase à retenir d'une notion s'affiche, l'enfant
  touche l'image qui l'illustre ; une phrase à la fois, l'image choisie disparaît.

Les images ne portent ni texte ni nom de fichier parlant : seule leur adresse est envoyée, la
réponse reste dans la solution. Sans au moins trois notions illustrées, ces jeux ne sont pas
proposés ; une image refusée par le parent n'arrive jamais ici.
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
    InvalidResponse,
    ResponseModel,
    parse_response,
)
from app.domain.errors import ErrorType
from app.domain.knowledge import KnowledgeUnit
from app.domain.text import normalize


class PicturePairsResponse(ResponseModel):
    # [image, mot] ; une image sans mot est ratée.
    pairs: list[tuple[str, str]] = Field(max_length=10)


class PictureFindResponse(ResponseModel):
    # [phrase, image touchée] dans l'ordre des phrases ; une phrase sans image est ratée.
    answers: list[tuple[str, str]] = Field(max_length=10)


def _images(activity: BuiltActivity) -> dict[str, str]:
    return {p["id"]: p["image"] for p in activity.payload.get("pictures", [])}


class _PictureGame(ActivityType):
    knowledge_types = ALL_TYPES
    multi_knowledge = True
    min_units = 3
    max_units = 5

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return unit.picture is not None

    def _can_combine(self, units: list[KnowledgeUnit], difficulty: int) -> bool:
        # Deux mots (ou deux phrases) identiques, ou la même image deux fois : jeu ambigu.
        return (
            len({u.id for u in units}) == len(units)
            and len({u.picture for u in units}) == len(units)
            and len({normalize(self._clue(u)) for u in units}) == len(units)
        )

    @staticmethod
    def _clue(unit: KnowledgeUnit) -> str:
        return unit.item.label

    @staticmethod
    def _pictures(
        units: list[KnowledgeUnit], rng: random.Random
    ) -> tuple[list[dict[str, str]], dict[str, str]]:
        """Images mélangées, numérotées p1, p2… ; et la notion de chaque image."""
        shuffled = list(units)
        rng.shuffle(shuffled)
        pictures, knowledge_by_picture = [], {}
        for i, unit in enumerate(shuffled, start=1):
            pictures.append({"id": f"p{i}", "image": str(unit.picture)})
            knowledge_by_picture[f"p{i}"] = unit.id
        return pictures, knowledge_by_picture


class PictureMatch(_PictureGame):
    """« Image et mot » : relier chaque image au mot qu'elle montre."""

    code = ActivityCode.PICTURE_MATCH
    difficulties = frozenset({1})
    base_duration_s = 45

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        pictures, knowledge_by_picture = self._pictures(units, rng)
        words = [(u.id, u.item.label) for u in units]
        rng.shuffle(words)
        word_ids = {unit_id: f"w{i}" for i, (unit_id, _) in enumerate(words, start=1)}
        labels = {word_ids[unit_id]: label for unit_id, label in words}
        expected = {p: word_ids[k] for p, k in knowledge_by_picture.items()}
        payload = {
            "prompt": "Relie chaque image au mot qui lui correspond.",
            "pictures": pictures,
            "words": [{"id": word_ids[unit_id], "text": label} for unit_id, label in words],
        }
        solution = {
            "expected": expected,
            "knowledge_by_picture": knowledge_by_picture,
            "word_texts": labels,
            "display": " ; ".join(f"image {p[1:]} : {labels[w]}" for p, w in expected.items()),
        }
        return payload, solution

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        given = parse_response(PicturePairsResponse, response).pairs
        expected: dict[str, str] = activity.solution["expected"]
        pictures = [p for p, _ in given]
        if len(set(pictures)) != len(pictures):
            raise InvalidResponse("une image a reçu deux mots")
        if not set(pictures) <= set(expected) or not {w for _, w in given} <= set(expected.values()):
            raise InvalidResponse("identifiant inconnu")
        answers = dict(given)
        labels: dict[str, str] = activity.solution["word_texts"]
        evidence: dict[str, float] = {}
        details = []
        for picture, word in expected.items():
            correct = answers.get(picture) == word
            evidence[activity.solution["knowledge_by_picture"][picture]] = 1.0 if correct else 0.0
            details.append(
                {
                    "id": picture,
                    "text": f"Image {picture[1:]}",
                    "correct": correct,
                    "expected": labels[word],
                    "image": _images(activity).get(picture),
                }
            )
        return Grade(
            score=sum(evidence.values()) / len(expected),
            evidence=evidence,
            errors={k: ErrorType.CONFUSION for k, result in evidence.items() if result < 1},
            correct_answer=activity.solution["display"],
            details=details,
        )


class PictureFind(_PictureGame):
    """« Quelle image ? » : une phrase à retenir à la fois, toucher l'image qui l'illustre."""

    code = ActivityCode.PICTURE_FIND
    difficulties = frozenset({2})
    base_duration_s = 50

    @staticmethod
    def _clue(unit: KnowledgeUnit) -> str:
        return unit.item.statement

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        pictures, knowledge_by_picture = self._pictures(units, rng)
        picture_of = {k: p for p, k in knowledge_by_picture.items()}
        clues = [(u.id, u.item.statement) for u in units]
        rng.shuffle(clues)
        clue_list, expected, knowledge_by_clue = [], {}, {}
        for i, (unit_id, text) in enumerate(clues, start=1):
            clue_id = f"c{i}"
            clue_list.append({"id": clue_id, "text": text})
            expected[clue_id] = picture_of[unit_id]
            knowledge_by_clue[clue_id] = unit_id
        payload = {
            "prompt": "Lis la phrase, puis touche l'image qui la montre.",
            "pictures": pictures,
            "clues": clue_list,
        }
        solution = {
            "expected": expected,
            "knowledge_by_clue": knowledge_by_clue,
            "clue_texts": {c["id"]: c["text"] for c in clue_list},
            "display": " ; ".join(f"{c['text']} → image {expected[c['id']][1:]}" for c in clue_list),
        }
        return payload, solution

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        given = parse_response(PictureFindResponse, response).answers
        expected: dict[str, str] = activity.solution["expected"]
        clues = [clue for clue, _ in given]
        if len(set(clues)) != len(clues):
            raise InvalidResponse("une phrase a reçu deux images")
        if not set(clues) <= set(expected) or not {p for _, p in given} <= set(expected.values()):
            raise InvalidResponse("identifiant inconnu")
        answers = dict(given)
        evidence: dict[str, float] = {}
        details = []
        for clue, picture in expected.items():
            correct = answers.get(clue) == picture
            evidence[activity.solution["knowledge_by_clue"][clue]] = 1.0 if correct else 0.0
            details.append(
                {
                    "id": clue,
                    "text": activity.solution["clue_texts"][clue],
                    "correct": correct,
                    "expected": f"image {picture[1:]}",
                    "image": _images(activity).get(picture),  # l'application montre la bonne image
                }
            )
        return Grade(
            score=sum(evidence.values()) / len(expected),
            evidence=evidence,
            errors={k: ErrorType.CONFUSION for k, result in evidence.items() if result < 1},
            correct_answer=activity.solution["display"],
            details=details,
        )
