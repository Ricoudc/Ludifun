"""Figures de géométrie dessinées par le code : des points sur une feuille, pour les exercices
d'alignement (« Les 3 points sont-ils alignés ? », « Entoure les 4 clous alignés », « Entoure
les points alignés avec les 2 points bleus »).

Une image dessinée par un générateur d'images ne garantit pas qu'un point est exactement sur la
droite : ici les points sont sur une grille de nombres entiers, et l'alignement se vérifie par le
calcul (produit en croix nul). Un point « pas aligné » est toujours assez loin de la droite pour
que cela se voie, et aucun autre alignement ne vient brouiller l'exercice.

Déterministe pour une graine donnée ; aucune IA, aucun réseau.
"""

import itertools
import math
import random
from dataclasses import dataclass

WIDTH, HEIGHT = 24, 14  # la feuille, en carreaux
MIN_GAP = 2.2  # deux points ne se touchent jamais
OFF_LINE = 1.4  # un point « pas aligné » est au moins à cette distance de la droite
TRIES = 400
LETTERS = "ABCDEFGHIJKLMNOP"
# Directions des droites : horizontales, verticales et obliques, pas seulement à 45°.
DIRECTIONS = (
    (1, 0),
    (0, 1),
    (1, 1),
    (1, -1),
    (2, 1),
    (2, -1),
    (1, 2),
    (1, -2),
    (3, 1),
    (3, -1),
    (3, 2),
    (3, -2),
)

Spot = tuple[int, int]


@dataclass(frozen=True)
class Point:
    id: str  # la lettre affichée à côté du point
    x: int
    y: int
    color: str = "black"  # "blue" : les deux points donnés

    def to_json(self) -> dict[str, object]:
        return {"id": self.id, "x": self.x, "y": self.y, "color": self.color}


def collinear(a: Spot, b: Spot, c: Spot) -> bool:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) == 0


def distance_to_line(p: Spot, a: Spot, b: Spot) -> float:
    cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    return abs(cross) / math.hypot(b[0] - a[0], b[1] - a[1])


def _far_enough(spot: Spot, others: list[Spot]) -> bool:
    return all(math.dist(spot, o) >= MIN_GAP for o in others)


def _line(rng: random.Random, count: int) -> list[Spot] | None:
    """`count` points alignés, régulièrement ou non espacés, dans la feuille."""
    dx, dy = rng.choice(DIRECTIONS)
    steps = sorted(rng.sample(range(0, 9), count))
    span_x, span_y = dx * steps[-1], dy * steps[-1]
    if span_x > WIDTH - 2 or abs(span_y) > HEIGHT - 2:
        return None
    x0 = rng.randint(1, WIDTH - 1 - span_x)
    y0 = rng.randint(1 - min(0, span_y), HEIGHT - 1 - max(0, span_y))
    spots = [(x0 + dx * s, y0 + dy * s) for s in steps]
    if any(math.dist(a, b) < MIN_GAP for a, b in itertools.pairwise(spots)):
        return None
    return spots


def _clear(spots: list[Spot], line: list[Spot]) -> bool:
    """Seuls les points de `line` sont alignés : un autre point est nettement à côté de leur
    droite, et aucun autre trio n'est exactement aligné."""
    chosen = set(line)
    a, b = line[0], line[-1]
    if any(distance_to_line(p, a, b) < OFF_LINE for p in spots if p not in chosen):
        return False
    return not any(collinear(*trio) for trio in itertools.combinations(spots, 3) if not set(trio) <= chosen)


def _scatter(rng: random.Random, line: list[Spot], total: int) -> list[Spot] | None:
    spots = list(line)
    for _ in range(TRIES):
        if len(spots) == total:
            return spots
        spot = (rng.randint(1, WIDTH - 1), rng.randint(1, HEIGHT - 1))
        if _far_enough(spot, spots) and _clear([*spots, spot], line):
            spots.append(spot)
    return None


def _named(spots: list[Spot], rng: random.Random, blue: frozenset[Spot] = frozenset()) -> list[Point]:
    """Les points dans un ordre mélangé, nommés A, B, C… de gauche à droite."""
    ordered = sorted(spots)
    return [
        Point(LETTERS[i], x, y, "blue" if (x, y) in blue else "black") for i, (x, y) in enumerate(ordered)
    ]


@dataclass(frozen=True)
class Figure:
    points: list[Point]
    answer: frozenset[str]  # les points alignés attendus (ou, pour oui/non, les trois points)
    aligned: bool = True  # oui/non : les trois points sont-ils alignés ?


def three_points(rng: random.Random, aligned: bool) -> Figure:
    """Trois points, alignés ou non (le point du milieu écarté d'au moins `OFF_LINE`)."""
    for _ in range(TRIES):
        line = _line(rng, 3)
        if line is None:
            continue
        if not aligned:
            a, middle, c = line
            moved = (middle[0] + rng.choice((-2, -1, 1, 2)), middle[1] + rng.choice((-2, -1, 1, 2)))
            if not (1 <= moved[0] <= WIDTH - 1 and 1 <= moved[1] <= HEIGHT - 1):
                continue
            if distance_to_line(moved, a, c) < OFF_LINE or not _far_enough(moved, [a, c]):
                continue
            line = [a, moved, c]
        points = _named(line, rng)
        return Figure(points, frozenset(p.id for p in points), aligned)
    raise ValueError("figure impossible")  # pragma: no cover - la grille laisse toujours de la place


def aligned_among(rng: random.Random, count: int, total: int) -> Figure:
    """`count` points alignés parmi `total` : aucun autre alignement de trois points."""
    for _ in range(TRIES):
        line = _line(rng, count)
        spots = _scatter(rng, line, total) if line else None
        if line is None or spots is None:
            continue
        points = _named(spots, rng)
        on_line = set(line)
        return Figure(points, frozenset(p.id for p in points if (p.x, p.y) in on_line))
    raise ValueError("figure impossible")  # pragma: no cover


def aligned_with_blue(rng: random.Random, total: int) -> Figure:
    """Deux points bleus et, sur leur droite, 2 ou 3 autres points à trouver parmi `total`."""
    for _ in range(TRIES):
        line = _line(rng, rng.choice((4, 5)))
        spots = _scatter(rng, line, total) if line else None
        if line is None or spots is None:
            continue
        blue = frozenset(rng.sample(line, 2))
        points = _named(spots, rng, blue)
        on_line = set(line) - blue
        return Figure(points, frozenset(p.id for p in points if (p.x, p.y) in on_line))
    raise ValueError("figure impossible")  # pragma: no cover


def listed(ids: frozenset[str] | list[str]) -> str:
    """« A, C et F »."""
    names = sorted(ids)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " et " + names[-1]
