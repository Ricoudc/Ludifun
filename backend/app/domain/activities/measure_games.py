"""Mesure et géométrie dessinées par l'application, corrigées par le code (aucune IA) :

- « Mesurer à la règle » (RULER) : un segment posé sur une règle graduée de 15 cm ; l'enfant
  choisit sa longueur. Difficulté 1 : le segment part du 0, en centimètres ; 2 : il part d'une
  autre graduation (l'erreur classique est de lire le nombre au bout) ; 3 : en centimètres et
  millimètres (à partir du CE2).
- « Symétrie » (SYMMETRY) : une figure sur un quadrillage, d'un côté d'un axe ; l'enfant
  touche les cases de l'autre côté pour la compléter. Faire glisser la figure au lieu de la
  retourner est reconnu et expliqué.

Proposés pour une notion de maths sur les longueurs ou la symétrie (thème choisi par l'IA ou
mots de la notion, `app.domain.math_generator.topics`).
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
    feedback,
    parse_response,
)
from app.domain.activities.math_games import _choices, _grade_choice, _grade_of, _rank, _result, _topics
from app.domain.errors import ErrorType
from app.domain.knowledge import Grade as SchoolGrade
from app.domain.knowledge import KnowledgeUnit
from app.domain.math_generator import Topic

# --------------------------------------------------------------------------- #
# Mesurer à la règle
# --------------------------------------------------------------------------- #

RULER_CM = 15  # longueur de la règle dessinée


def length_text(mm: int, with_mm: bool) -> str:
    """« 7 cm », « 5 cm 3 mm », « 8 mm »."""
    cm, rest = divmod(mm, 10)
    if not with_mm or rest == 0:
        return f"{cm} cm"
    return f"{rest} mm" if cm == 0 else f"{cm} cm {rest} mm"


class Ruler(ActivityType):
    code = ActivityCode.RULER
    knowledge_types = ALL_TYPES
    difficulties = frozenset({1, 2, 3})
    base_duration_s = 15

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return Topic.LENGTH in _topics(unit)

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        with_mm = difficulty == 3 and _rank(_grade_of(unit)) >= _rank(SchoolGrade.CE2)
        for _ in range(50):
            start = 0 if difficulty == 1 else 10 * rng.randint(1, 5)
            if with_mm:
                length = rng.choice([n for n in range(21, 100) if n % 10])
            else:
                length = 10 * rng.randint(2, 12 if difficulty == 1 else 9)
            end = start + length
            if end > RULER_CM * 10:
                continue
            answer = length_text(length, with_mm)
            cm, rest = divmod(length, 10)
            wrong: list[tuple[str, ErrorType]] = []
            if start:
                wrong.append((length_text(end, with_mm), ErrorType.READING))  # le nombre au bout
            if with_mm:
                wrong += [
                    (f"{length} cm", ErrorType.CONFUSION),  # millimètres lus comme des centimètres
                    (length_text(rest * 10 + cm, True), ErrorType.CONFUSION),  # cm et mm inversés
                    (length_text(length + 1, True), ErrorType.IMPRECISION),
                    (length_text(length - 1, True), ErrorType.IMPRECISION),
                ]
            else:
                wrong += [
                    (length_text(length + 10, False), ErrorType.METHOD),  # graduations comptées
                    (length_text(length - 10, False), ErrorType.CALCULATION),
                    (length_text(length + 20, False), ErrorType.CALCULATION),
                ]
            choices = _choices(answer, [w for w, _ in wrong], rng)
            if choices is None:
                continue
            listed, answer_id = choices
            kinds: dict[str, str] = {}
            for shown, kind in wrong:  # deux erreurs qui donnent le même nombre : la première
                kinds.setdefault(shown, kind.value)
            how = (
                f"Il part du 0 et s'arrête à {length_text(end, with_mm)}."
                if not start
                else f"Il part de {start // 10} et s'arrête à {length_text(end, with_mm)}, "
                f"donc on enlève {start // 10} cm."
            )
            payload = {
                "prompt": "Combien mesure le segment rouge ?",
                "ruler_cm": RULER_CM,
                "start_mm": start,
                "length_mm": length,
                "choices": listed,
            }
            return payload, {
                "choice_id": answer_id,
                "misconceptions": {c["id"]: kinds[c["text"]] for c in listed if c["id"] != answer_id},
                "display": f"Le segment mesure {answer}. {how}",
                **feedback(unit),
            }
        raise ValueError("règle impossible")  # pragma: no cover

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        score, error = _grade_choice(activity, response)
        return _result(activity, score, error)


# --------------------------------------------------------------------------- #
# Symétrie
# --------------------------------------------------------------------------- #

HALF = 5  # cases d'un côté de l'axe
OTHER_SIDE = 8  # cases dans l'autre sens
SYMMETRY_SIZE = {1: (3, 4), 2: (5, 7), 3: (6, 8)}  # cases de la figure, selon la difficulté
SLID = (
    "Tu as fait glisser la figure. Par symétrie, elle se retourne comme dans un miroir. "
    "Chaque case est à la même distance de l'axe, de l'autre côté."
)

Cell = tuple[int, int]


def mirror(cell: Cell, axis: str) -> Cell:
    """Case symétrique par rapport à l'axe (entre les colonnes ou les lignes 4 et 5)."""
    x, y = cell
    return (2 * HALF - 1 - x, y) if axis == "vertical" else (x, 2 * HALF - 1 - y)


def slide(cell: Cell, axis: str) -> Cell:
    """La case où l'aurait mise une figure glissée de l'autre côté au lieu d'être retournée."""
    x, y = cell
    return (x + HALF, y) if axis == "vertical" else (x, y + HALF)


def grid_size(axis: str) -> tuple[int, int]:
    """Largeur et hauteur du quadrillage."""
    return (2 * HALF, OTHER_SIDE) if axis == "vertical" else (OTHER_SIDE, 2 * HALF)


def _shape(axis: str, size: int, on_axis: bool, rng: random.Random) -> set[Cell]:
    """Une figure d'un seul tenant, du côté gauche (ou du haut) de l'axe."""

    def inside(cell: Cell) -> bool:
        along, across = (cell[1], cell[0]) if axis == "vertical" else cell
        return 0 <= along < OTHER_SIDE and 0 <= across < HALF

    def make(along: int, across: int) -> Cell:
        return (across, along) if axis == "vertical" else (along, across)

    first = make(rng.randrange(1, OTHER_SIDE - 1), HALF - 1 if on_axis else rng.randrange(1, HALF - 1))
    shape = {first}
    while len(shape) < size:
        x, y = rng.choice(sorted(shape))
        neighbour = rng.choice(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
        if inside(neighbour):
            shape.add(neighbour)
    return shape


class SymmetrySelection(ResponseModel):
    selected: list[tuple[int, int]] = Field(max_length=HALF * OTHER_SIDE)


class Symmetry(ActivityType):
    code = ActivityCode.SYMMETRY
    knowledge_types = ALL_TYPES
    difficulties = frozenset({1, 2, 3})
    base_duration_s = 35

    def _has_material(self, unit: KnowledgeUnit) -> bool:
        return Topic.SYMMETRY in _topics(unit)

    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unit = units[0]
        axis = "horizontal" if difficulty == 3 else "vertical"
        for _ in range(100):
            shape = _shape(axis, rng.randint(*SYMMETRY_SIZE[difficulty]), difficulty < 3, rng)
            expected = {mirror(c, axis) for c in shape}
            if {slide(c, axis) for c in shape} != expected:  # glisser ou retourner : différent
                break
        else:  # pragma: no cover
            raise ValueError("figure impossible")
        width, height = grid_size(axis)
        side = "à droite de l'axe" if axis == "vertical" else "sous l'axe"
        payload = {
            "prompt": f"Complète la figure par symétrie : touche les cases {side}.",
            "width": width,
            "height": height,
            "axis": axis,
            "filled": sorted([list(c) for c in shape]),
        }
        display = (
            f"Chaque case a sa jumelle de l'autre côté de l'axe, à la même distance, "
            f"soit {len(expected)} cases à colorier."
        )
        return payload, {
            "expected": sorted([list(c) for c in expected]),
            "slid": sorted([list(slide(c, axis)) for c in shape]),
            "display": display,
            **feedback(unit),
        }

    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        payload, solution = activity.payload, activity.solution
        selected = set(parse_response(SymmetrySelection, response).selected)
        width, height, axis = payload["width"], payload["height"], payload["axis"]
        for x, y in selected:
            mine = x >= HALF if axis == "vertical" else y >= HALF
            if not (0 <= x < width and 0 <= y < height and mine):
                raise InvalidResponse("case hors de la moitié à compléter")
        expected = {(x, y) for x, y in solution["expected"]}
        explanation = None
        if selected == expected:
            score = 1.0
        elif selected == {(x, y) for x, y in solution["slid"]}:
            score, explanation = 0.0, SLID
        else:
            found = len(selected & expected) - len(selected - expected)
            score = min(0.75, max(0.0, round(found / len(expected), 2)))
        return _result(activity, score, ErrorType.METHOD, explanation)
