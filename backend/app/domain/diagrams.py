"""Figures exactes et schémas légendés, dessinés par le code (spécification technique §5.61).

Un moteur d'images (Stable Diffusion, Pollinations) dessine une scène « à la manière de » : il
ne sait ni tracer un carré aux quatre côtés égaux, ni marquer un angle droit, ni écrire une
légende juste. Ce qui doit être exact pour être appris est donc dessiné ici, par le calcul :

- **figures de géométrie** (leçons de mathématiques) : carré, rectangle, losange,
  parallélogramme, trapèze, triangles (quelconque, rectangle, isocèle, équilatéral), cercle,
  angles, droites parallèles et perpendiculaires, segment / droite / demi-droite, axe de
  symétrie, cube, pavé droit, périmètre, aire ; avec le codage du cahier (petits traits sur les
  côtés égaux, carré de l'angle droit, sommets nommés) ;
- **schémas légendés** de la bibliothèque de figures (étape 22 : volcan, plante, squelette,
  cartes…) : les zones dont parle la leçon en couleur, numérotées, avec leur légende.

Deux usages : l'image d'une notion (jeux « apprendre par l'image ») ne porte aucun nom — la
réponse serait écrite dessus ; l'image de la leçon est une fiche mémo : chaque figure avec son
nom et ce qu'il faut en retenir, ou le schéma et sa légende.

Domaine pur : des points et des textes, déterministes pour une variante donnée ; le rendu en
PNG est fait par `app.services.drawing_render`.
"""

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from app.domain.text import normalize

if TYPE_CHECKING:
    from app.domain.figures import FigureLibrary

Point = tuple[float, float]

INK = "#1f2933"
ACCENT = "#e8552d"  # ce qu'il faut regarder : codage, côté mesuré
BLUE = "#2f6fdf"
FILL = "#e8f1ff"
GREY = "#d9dde3"
WIDTH, HEIGHT = 600, 440  # une figure seule
VERSION = 1  # version des dessins (enregistrée avec l'image)


@dataclass(frozen=True)
class Stroke:
    """Polygone (`closed`) ou ligne brisée."""

    points: tuple[Point, ...]
    closed: bool = True
    fill: str | None = None
    color: str = INK
    width: float = 5
    dashed: bool = False


@dataclass(frozen=True)
class Disc:
    center: Point
    radius: float
    fill: str | None = None
    color: str = INK
    width: float = 5
    dashed: bool = False


@dataclass(frozen=True)
class Label:
    text: str
    at: Point
    size: int = 30
    color: str = INK
    bold: bool = False


Item = Stroke | Disc | Label


@dataclass(frozen=True)
class Drawing:
    key: str  # « carre », « figure:volcan »
    name: str  # « Le carré » (jamais dessiné sur l'image d'une notion)
    facts: tuple[str, ...]  # ce qu'il faut retenir (fiche mémo seulement)
    alt: str  # pour le parent et la lecture d'écran
    width: float
    height: float
    items: tuple[Item, ...]


# --------------------------------------------------------------------------- #
# Outils de tracé
# --------------------------------------------------------------------------- #


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def _unit(v: Point) -> Point:
    n = math.hypot(*v) or 1.0
    return (v[0] / n, v[1] / n)


def _along(a: Point, b: Point, t: float) -> Point:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _rotate(
    points: Sequence[Point], angle_deg: float, center: Point = (WIDTH / 2, HEIGHT / 2)
) -> list[Point]:
    a = math.radians(angle_deg)
    c, s = math.cos(a), math.sin(a)
    return [
        (
            center[0] + (x - center[0]) * c - (y - center[1]) * s,
            center[1] + (x - center[0]) * s + (y - center[1]) * c,
        )
        for x, y in points
    ]


def ticks(a: Point, b: Point, count: int, size: float = 14) -> list[Item]:
    """`count` petits traits au milieu de [ab] : les côtés qui ont autant de traits sont égaux."""
    d = _unit(_sub(b, a))
    n = (-d[1], d[0])
    middle = _along(a, b, 0.5)
    gap = 9.0
    items: list[Item] = []
    for i in range(count):
        offset = (i - (count - 1) / 2) * gap
        c = (middle[0] + d[0] * offset, middle[1] + d[1] * offset)
        items.append(
            Stroke(
                ((c[0] - n[0] * size, c[1] - n[1] * size), (c[0] + n[0] * size, c[1] + n[1] * size)),
                closed=False,
                color=ACCENT,
                width=4,
            )
        )
    return items


def right_angle(vertex: Point, p1: Point, p2: Point, size: float = 24) -> Item:
    """Le petit carré qui code un angle droit en `vertex`."""
    u, v = _unit(_sub(p1, vertex)), _unit(_sub(p2, vertex))
    a = (vertex[0] + u[0] * size, vertex[1] + u[1] * size)
    b = (vertex[0] + (u[0] + v[0]) * size, vertex[1] + (u[1] + v[1]) * size)
    c = (vertex[0] + v[0] * size, vertex[1] + v[1] * size)
    return Stroke((a, b, c), closed=False, color=ACCENT, width=4)


def angle_arc(vertex: Point, p1: Point, p2: Point, radius: float = 40) -> Item:
    a1 = math.atan2(p1[1] - vertex[1], p1[0] - vertex[0])
    a2 = math.atan2(p2[1] - vertex[1], p2[0] - vertex[0])
    sweep = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi  # le plus petit des deux angles
    steps = 16
    points = tuple(
        (
            vertex[0] + radius * math.cos(a1 + sweep * i / steps),
            vertex[1] + radius * math.sin(a1 + sweep * i / steps),
        )
        for i in range(steps + 1)
    )
    return Stroke(points, closed=False, color=ACCENT, width=4)


def chevrons(a: Point, b: Point, count: int = 1) -> list[Item]:
    """Petites flèches au milieu de [ab] : les côtés qui en ont sont parallèles."""
    d = _unit(_sub(b, a))
    n = (-d[1], d[0])
    items: list[Item] = []
    for i in range(count):
        tip = _along(a, b, 0.5 + 0.03 * i)
        back = (tip[0] - d[0] * 14, tip[1] - d[1] * 14)
        items.append(
            Stroke(
                ((back[0] + n[0] * 10, back[1] + n[1] * 10), tip, (back[0] - n[0] * 10, back[1] - n[1] * 10)),
                closed=False,
                color=ACCENT,
                width=4,
            )
        )
    return items


def vertex_names(points: Sequence[Point], names: str = "ABCDEFGH", distance: float = 30) -> list[Item]:
    """Les sommets nommés, écrits à l'extérieur de la figure."""
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    items: list[Item] = []
    for p, name in zip(points, names, strict=False):
        d = _unit((p[0] - cx, p[1] - cy))
        items.append(Label(name, (p[0] + d[0] * distance, p[1] + d[1] * distance), size=28, bold=True))
    return items


def _polygon(points: Sequence[Point], fill: str = FILL) -> Stroke:
    return Stroke(tuple(points), fill=fill)


def _sides(points: Sequence[Point]) -> list[tuple[Point, Point]]:
    return [(points[i], points[(i + 1) % len(points)]) for i in range(len(points))]


# --------------------------------------------------------------------------- #
# Les figures de géométrie
# --------------------------------------------------------------------------- #


def _quadrilateral(
    points: list[Point], marks: Sequence[int], right: bool, letters: bool = True
) -> list[Item]:
    """`marks[i]` : nombre de traits sur le côté i (0 : aucun) ; `right` : quatre angles droits."""
    items: list[Item] = [_polygon(points)]
    for (a, b), count in zip(_sides(points), marks, strict=True):
        items += ticks(a, b, count) if count else []
    if right:
        items += [right_angle(points[i], points[i - 1], points[(i + 1) % 4]) for i in range(4)]
    return items + (vertex_names(points) if letters else [])


def _square(variant: int) -> list[Item]:
    side = 250
    x, y = (WIDTH - side) / 2, (HEIGHT - side) / 2
    points = [(x, y + side), (x + side, y + side), (x + side, y), (x, y)]
    return _quadrilateral(_rotate(points, (0, 18, -12)[variant % 3]), (1, 1, 1, 1), right=True)


def _rectangle(variant: int) -> list[Item]:
    w, h = 360, 200
    x, y = (WIDTH - w) / 2, (HEIGHT - h) / 2
    points = [(x, y + h), (x + w, y + h), (x + w, y), (x, y)]
    return _quadrilateral(_rotate(points, (0, 10, -8)[variant % 3]), (2, 1, 2, 1), right=True)


def _rhombus(variant: int) -> list[Item]:
    cx, cy, dx, dy = WIDTH / 2, HEIGHT / 2, 190, 125
    points = _rotate([(cx, cy + dy), (cx + dx, cy), (cx, cy - dy), (cx - dx, cy)], (0, 15, -15)[variant % 3])
    items = _quadrilateral(points, (1, 1, 1, 1), right=False)
    items.insert(1, Stroke((points[0], points[2]), closed=False, color=BLUE, width=3, dashed=True))
    items.insert(2, Stroke((points[1], points[3]), closed=False, color=BLUE, width=3, dashed=True))
    center = _along(points[0], points[2], 0.5)
    items.append(right_angle(center, points[1], points[2], size=18))
    return items


def _parallelogram(variant: int) -> list[Item]:
    points = _rotate([(90, 340), (390, 340), (510, 100), (210, 100)], (0, 8, -8)[variant % 3])
    items = _quadrilateral(points, (2, 1, 2, 1), right=False)
    return items + chevrons(points[0], points[1]) + chevrons(points[3], points[2])


def _trapezoid(variant: int) -> list[Item]:
    points = _rotate([(70, 340), (530, 340), (410, 110), (190, 110)], (0, 6, -6)[variant % 3])
    return (
        _quadrilateral(points, (0, 0, 0, 0), right=False)
        + chevrons(points[0], points[1])
        + chevrons(points[3], points[2])
    )


def _triangle(
    points: list[Point], marks: Sequence[int] = (0, 0, 0), right_at: int | None = None
) -> list[Item]:
    items: list[Item] = [_polygon(points)]
    for (a, b), count in zip(_sides(points), marks, strict=True):
        items += ticks(a, b, count) if count else []
    if right_at is not None:
        items.append(right_angle(points[right_at], points[right_at - 1], points[(right_at + 1) % 3]))
    return items + vertex_names(points)


def _any_triangle(variant: int) -> list[Item]:
    return _triangle(_rotate([(90, 350), (500, 330), (250, 85)], (0, 10, -10)[variant % 3]))


def _right_triangle(variant: int) -> list[Item]:
    return _triangle(_rotate([(130, 350), (470, 350), (130, 90)], (0, 12, -12)[variant % 3]), right_at=0)


def _isosceles(variant: int) -> list[Item]:
    return _triangle(_rotate([(150, 350), (450, 350), (300, 70)], (0, 10, -10)[variant % 3]), marks=(0, 1, 1))


def _equilateral(variant: int) -> list[Item]:
    side = 330
    top = HEIGHT / 2 + side * math.sqrt(3) / 4 - side * math.sqrt(3) / 2
    base = HEIGHT / 2 + side * math.sqrt(3) / 4
    points = [(WIDTH / 2 - side / 2, base), (WIDTH / 2 + side / 2, base), (WIDTH / 2, top)]
    return _triangle(_rotate(points, (0, 12, -12)[variant % 3]), marks=(1, 1, 1))


def _circle(variant: int) -> list[Item]:
    center, r = (WIDTH / 2, HEIGHT / 2), 160.0
    a = math.radians((-35, -60, -20)[variant % 3])
    on = (center[0] + r * math.cos(a), center[1] + r * math.sin(a))
    left, right = (center[0] - r, center[1] + 0.0), (center[0] + r, center[1] + 0.0)
    return [
        Disc(center, r, fill=FILL),
        Stroke((left, right), closed=False, color=BLUE, width=4, dashed=True),  # diamètre
        Stroke((center, on), closed=False, color=ACCENT, width=5),  # rayon
        Disc(center, 6, fill=INK, width=0),
        Label("O", (center[0] - 6, center[1] + 28), size=28, bold=True),
        Label("A", (on[0] + 22 * math.cos(a), on[1] + 22 * math.sin(a)), size=28, bold=True),
        Label("B", (left[0] - 24, left[1]), size=28, bold=True),
        Label("C", (right[0] + 24, right[1]), size=28, bold=True),
    ]


def _angle(opening: float, origin: Point = (170, 330), length: float = 300) -> list[Item]:
    end1 = (origin[0] + length, origin[1])
    a = math.radians(-opening)
    end2 = (origin[0] + length * math.cos(a), origin[1] + length * math.sin(a))
    rays = Stroke((end2, origin, end1), closed=False)
    mark = right_angle(origin, end1, end2, size=34) if opening == 90 else angle_arc(origin, end1, end2, 50)
    return [rays, mark]


def _right_angle_shape(variant: int) -> list[Item]:
    return _angle(90)


def _acute(variant: int) -> list[Item]:
    return _angle((40, 55, 30)[variant % 3])


def _obtuse(variant: int) -> list[Item]:
    return _angle((130, 145, 115)[variant % 3], origin=(330, 330), length=240)


def _angles(variant: int) -> list[Item]:
    """Les trois angles côte à côte : aigu, droit, obtus."""
    items: list[Item] = []
    for i, opening in enumerate((45, 90, 135)):
        x = 60 + i * 190 + (60 if opening == 135 else 0)
        items += _angle(opening, origin=(x, 330), length=150)
    return items


def _parallels(variant: int) -> list[Item]:
    tilt = (0, -12, 10)[variant % 3]
    l1 = _rotate([(40, 150), (560, 150)], tilt)
    l2 = _rotate([(40, 300), (560, 300)], tilt)
    items: list[Item] = [Stroke(tuple(l1), closed=False), Stroke(tuple(l2), closed=False)]
    for t in (0.3, 0.7):  # même écart partout : deux perpendiculaires de même longueur
        a, b = _along(l1[0], l1[1], t), _along(l2[0], l2[1], t)
        items.append(Stroke((a, b), closed=False, color=BLUE, width=3, dashed=True))
        items.append(right_angle(b, a, l2[1], size=16))
        items += ticks(a, b, 1, size=10)
    items += [
        Label("(d1)", (l1[1][0] - 10, l1[1][1] - 26), size=26),
        Label("(d2)", (l2[1][0] - 10, l2[1][1] - 26), size=26),
    ]
    return items


def _perpendiculars(variant: int) -> list[Item]:
    tilt = (0, 25, -20)[variant % 3]
    center = (WIDTH / 2, HEIGHT / 2)
    l1 = _rotate([(60, center[1]), (540, center[1])], tilt)
    l2 = _rotate([(center[0], 30), (center[0], 410)], tilt)
    return [
        Stroke(tuple(l1), closed=False),
        Stroke(tuple(l2), closed=False),
        right_angle(center, l1[1], l2[0], size=30),
        Label("(d1)", (l1[1][0] - 20, l1[1][1] + 28), size=26),
        Label("(d2)", (l2[0][0] + 36, l2[0][1] + 10), size=26),
    ]


def _cross(p: Point) -> Item:
    return Stroke(
        ((p[0] - 9, p[1] - 9), (p[0] + 9, p[1] + 9), p, (p[0] - 9, p[1] + 9), (p[0] + 9, p[1] - 9)),
        closed=False,
        width=3,
    )


def _lines(kinds: Sequence[str]) -> list[Item]:
    """Segment [AB], droite (AB), demi-droite [AB) : une ligne chacun."""
    items: list[Item] = []
    rows = len(kinds)
    for i, kind in enumerate(kinds):
        y = HEIGHT * (i + 1) / (rows + 1)
        a, b = (200.0, y), (400.0, y)
        start = 30.0 if kind == "droite" else a[0]
        end = 570.0 if kind in ("droite", "demi-droite") else b[0]
        items.append(Stroke(((start, y), (end, y)), closed=False))
        items += [
            _cross(a),
            _cross(b),
            Label("A", (a[0], y - 30), size=26, bold=True),
            Label("B", (b[0], y - 30), size=26, bold=True),
        ]
        if kind == "segment":
            items += [
                Stroke(((x, y - 14), (x, y + 14)), closed=False, color=ACCENT, width=4) for x in (a[0], b[0])
            ]
        notation = {"segment": "[AB]", "droite": "(AB)", "demi-droite": "[AB)"}[kind]
        items.append(Label(notation, (300, y + 34), size=26, color=ACCENT, bold=True))
    return items


def _segment(variant: int) -> list[Item]:
    return _lines(["segment"])


def _line(variant: int) -> list[Item]:
    return _lines(["droite"])


def _half_line(variant: int) -> list[Item]:
    return _lines(["demi-droite"])


def _symmetry(variant: int) -> list[Item]:
    """Une figure symétrique (un sapin) et son axe en pointillés."""
    cx = WIDTH / 2
    right = [(cx, 50), (cx + 90, 160), (cx + 45, 160), (cx + 130, 290), (cx + 30, 290), (cx + 30, 380)]
    left = [(2 * cx - x, y) for x, y in reversed(right[1:])]
    shape = [*right, *left]
    return [
        Stroke(tuple(shape), fill="#d8f0d2", color="#2e7d32"),
        Stroke(((cx, 20), (cx, 420)), closed=False, color=ACCENT, width=4, dashed=True),
    ]


def _solid(front: list[Point], depth: Point, square: bool) -> list[Item]:
    back = [(x + depth[0], y + depth[1]) for x, y in front]
    hidden = 0  # le sommet avant-bas-gauche : ses arêtes vers l'arrière sont cachées
    items: list[Item] = [_polygon(front)]
    visible_back = [back[1], back[2], back[3]]
    items.append(Stroke(tuple(visible_back), closed=False))
    items += [Stroke((front[i], back[i]), closed=False) for i in (1, 2, 3)]
    # Arêtes cachées en pointillés.
    items.append(Stroke((back[0], back[1]), closed=False, color="#7b8794", width=3, dashed=True))
    items.append(Stroke((back[0], back[3]), closed=False, color="#7b8794", width=3, dashed=True))
    items.append(Stroke((front[hidden], back[hidden]), closed=False, color="#7b8794", width=3, dashed=True))
    if square:
        items += ticks(front[0], front[1], 1) + ticks(front[1], front[2], 1)
    return items


def _cube(variant: int) -> list[Item]:
    s = 210
    x, y = 150, 380
    return _solid([(x, y), (x + s, y), (x + s, y - s), (x, y - s)], (95, -75), square=True)


def _cuboid(variant: int) -> list[Item]:
    w, h = 280, 170
    x, y = 110, 370
    return _solid([(x, y), (x + w, y), (x + w, y - h), (x, y - h)], (110, -85), square=False)


def _perimeter(variant: int) -> list[Item]:
    w, h = 360, 200
    x, y = (WIDTH - w) / 2, (HEIGHT - h) / 2
    points = ((x, y + h), (x + w, y + h), (x + w, y), (x, y))
    return [
        Stroke(points, fill=FILL, color=ACCENT, width=10),  # le tour, en couleur
        *chevrons(points[0], points[1]),
        *chevrons(points[1], points[2]),
        *chevrons(points[2], points[3]),
        *chevrons(points[3], points[0]),
    ]


AREA_GRID = (6, 4)  # carreaux de l'aire : 6 × 4


def _area(variant: int) -> list[Item]:
    cols, rows = AREA_GRID
    side = 56
    x0, y0 = (WIDTH - cols * side) / 2, (HEIGHT - rows * side) / 2
    items: list[Item] = [
        Stroke(
            (
                (x0 + c * side, y0 + r * side),
                (x0 + (c + 1) * side, y0 + r * side),
                (x0 + (c + 1) * side, y0 + (r + 1) * side),
                (x0 + c * side, y0 + (r + 1) * side),
            ),
            fill="#ffe3d6" if (c + r) % 2 else "#ffd0bb",
            color="#c4c9d0",
            width=2,
        )
        for r in range(rows)
        for c in range(cols)
    ]
    items.append(
        Stroke(
            ((x0, y0), (x0 + cols * side, y0), (x0 + cols * side, y0 + rows * side), (x0, y0 + rows * side))
        )
    )
    return items


@dataclass(frozen=True)
class Shape:
    key: str
    name: str
    pattern: re.Pattern[str]  # sur le texte normalisé (minuscules, sans accents)
    draw: Callable[[int], list[Item]]
    facts: tuple[str, ...]
    alt: str


def _p(regex: str) -> re.Pattern[str]:
    return re.compile(regex)


# Du plus précis au plus général : « triangle rectangle » avant « rectangle » et « triangle ».
# Les unités (« mètre carré »), les directions (« à droite ») et les fractions ne sont pas des
# figures.
SHAPES: tuple[Shape, ...] = (
    Shape(
        "triangle-rectangle",
        "Le triangle rectangle",
        _p(r"\btriangles? rectangles?\b"),
        _right_triangle,
        ("Il a un angle droit.",),
        "Un triangle rectangle ABC, avec son angle droit marqué en A.",
    ),
    Shape(
        "triangle-isocele",
        "Le triangle isocèle",
        _p(r"\btriangles? isoceles?\b"),
        _isosceles,
        ("Il a deux côtés de même longueur.",),
        "Un triangle isocèle : deux côtés codés égaux.",
    ),
    Shape(
        "triangle-equilateral",
        "Le triangle équilatéral",
        _p(r"\btriangles? equilateral(?:aux|s)?\b"),
        _equilateral,
        ("Ses trois côtés ont la même longueur.", "Ses trois angles sont égaux."),
        "Un triangle équilatéral : les trois côtés codés égaux.",
    ),
    Shape(
        "carre",
        "Le carré",
        _p(r"(?<!metre )(?<!metres )(?<!au )(?<!racine )\bcarres?\b(?! parfait)"),
        _square,
        ("Il a 4 côtés de même longueur.", "Il a 4 angles droits."),
        "Un carré ABCD : quatre côtés codés égaux et quatre angles droits.",
    ),
    Shape(
        "losange",
        "Le losange",
        _p(r"\blosanges?\b"),
        _rhombus,
        ("Il a 4 côtés de même longueur.", "Ses diagonales se coupent en formant un angle droit."),
        "Un losange ABCD : quatre côtés codés égaux, ses diagonales en pointillés.",
    ),
    Shape(
        "parallelogramme",
        "Le parallélogramme",
        _p(r"\bparallelogrammes?\b"),
        _parallelogram,
        ("Ses côtés opposés sont parallèles.", "Ses côtés opposés ont la même longueur."),
        "Un parallélogramme ABCD : côtés opposés parallèles et de même longueur.",
    ),
    Shape(
        "trapeze",
        "Le trapèze",
        _p(r"\btrapezes?\b"),
        _trapezoid,
        ("Il a deux côtés opposés parallèles : ses bases.",),
        "Un trapèze ABCD : deux côtés parallèles.",
    ),
    Shape(
        "rectangle",
        "Le rectangle",
        _p(r"(?<!triangle )\brectangles?\b"),
        _rectangle,
        ("Il a 4 angles droits.", "Ses côtés opposés ont la même longueur."),
        "Un rectangle ABCD : quatre angles droits, côtés opposés codés égaux.",
    ),
    Shape(
        "triangle",
        "Le triangle",
        _p(r"\btriangles?\b"),
        _any_triangle,
        ("Il a 3 côtés, 3 sommets et 3 angles.",),
        "Un triangle ABC.",
    ),
    Shape(
        "cercle",
        "Le cercle",
        _p(r"\b(cercles?|disques?|rayon|diametre|compas)\b"),
        _circle,
        ("O est le centre.", "[OA] est un rayon.", "[BC] est un diamètre : 2 fois le rayon."),
        "Un cercle de centre O, avec un rayon [OA] et un diamètre [BC].",
    ),
    Shape(
        "angle-droit",
        "L'angle droit",
        _p(r"\bangles? droits?\b"),
        _right_angle_shape,
        ("Il se vérifie avec l'équerre.",),
        "Un angle droit, marqué par un petit carré.",
    ),
    Shape(
        "angle-aigu",
        "L'angle aigu",
        _p(r"\bangles? aigus?\b"),
        _acute,
        ("Il est plus petit qu'un angle droit.",),
        "Un angle aigu, plus fermé qu'un angle droit.",
    ),
    Shape(
        "angle-obtus",
        "L'angle obtus",
        _p(r"\bangles? obtus\b"),
        _obtuse,
        ("Il est plus grand qu'un angle droit.",),
        "Un angle obtus, plus ouvert qu'un angle droit.",
    ),
    Shape(
        "angles",
        "Les angles",
        _p(r"\bangles?\b"),
        _angles,
        ("Aigu, droit, obtus : du plus fermé au plus ouvert.",),
        "Trois angles : aigu, droit et obtus.",
    ),
    Shape(
        "perpendiculaires",
        "Les droites perpendiculaires",
        _p(r"\bperpendiculaires?\b"),
        _perpendiculars,
        ("Elles se coupent en formant un angle droit.",),
        "Deux droites qui se coupent à angle droit.",
    ),
    Shape(
        "paralleles",
        "Les droites parallèles",
        _p(r"\b(droites?|segments?) paralleles?\b|\bparalleles?\b"),
        _parallels,
        ("Elles ne se coupent jamais : l'écart reste le même.",),
        "Deux droites parallèles, le même écart mesuré à deux endroits.",
    ),
    Shape(
        "demi-droite",
        "La demi-droite",
        _p(r"\bdemi droites?\b"),
        _half_line,
        ("[AB) commence en A et passe par B, sans fin.",),
        "Une demi-droite [AB).",
    ),
    Shape(
        "segment",
        "Le segment",
        _p(r"\bsegments?\b"),
        _segment,
        ("[AB] va de A à B : il a deux extrémités.",),
        "Un segment [AB].",
    ),
    Shape(
        "droite",
        "La droite",
        _p(r"\bdroites?\b"),
        _line,
        ("(AB) passe par A et B, sans fin des deux côtés.",),
        "Une droite (AB).",
    ),
    Shape(
        "symetrie",
        "L'axe de symétrie",
        _p(r"\b(symetrie|symetrique|symetriques|axe)\b"),
        _symmetry,
        ("Plié le long de l'axe, les deux moitiés se superposent.",),
        "Un sapin symétrique et son axe en pointillés.",
    ),
    Shape(
        "cube",
        "Le cube",
        _p(r"(?<!metre )(?<!metres )(?<!au )\bcubes?\b"),
        _cube,
        ("6 faces carrées, 12 arêtes, 8 sommets.",),
        "Un cube en perspective, arêtes cachées en pointillés.",
    ),
    Shape(
        "pave",
        "Le pavé droit",
        _p(r"\bpaves? droits?\b|\bparallelepipedes?\b"),
        _cuboid,
        ("6 faces rectangulaires, 12 arêtes, 8 sommets.",),
        "Un pavé droit en perspective, arêtes cachées en pointillés.",
    ),
    Shape(
        "perimetre",
        "Le périmètre",
        _p(r"\bperimetres?\b"),
        _perimeter,
        ("C'est la longueur du tour de la figure.",),
        "Un rectangle dont le tour est tracé en couleur.",
    ),
    Shape(
        "aire",
        "L'aire",
        _p(r"\baires?\b"),
        _area,
        (f"C'est la surface à l'intérieur : ici {AREA_GRID[0] * AREA_GRID[1]} carreaux.",),
        f"Un rectangle partagé en {AREA_GRID[0] * AREA_GRID[1]} carreaux.",
    ),
)
# « La droite graduée », « à droite », « la ligne droite » : pas des figures à dessiner.
_NOT_A_SHAPE = re.compile(
    r"\b(droite graduee|a droite|de droite|vers la droite|ligne droite|aire de jeux|axe gradue"
    r"|axe chronologique)\b"
)


def find_shape(text: str) -> Shape | None:
    """La figure dont parle `text` (le nom d'une notion de géométrie, une remarque du parent)."""
    key = normalize(text)
    key = _NOT_A_SHAPE.sub(" ", key)
    return next((s for s in SHAPES if s.pattern.search(key)), None)


def shape_drawing(shape: Shape, variant: int = 0) -> Drawing:
    """La figure seule, sans nom : l'image d'une notion (le nom serait la réponse des jeux)."""
    return Drawing(shape.key, shape.name, shape.facts, shape.alt, WIDTH, HEIGHT, tuple(shape.draw(variant)))


# --------------------------------------------------------------------------- #
# Fiche mémo : titre, figures et ce qu'il faut retenir
# --------------------------------------------------------------------------- #


def _shift(item: Item, dx: float, dy: float, k: float = 1.0) -> Item:
    def move(p: Point) -> Point:
        return (p[0] * k + dx, p[1] * k + dy)

    if isinstance(item, Stroke):
        return replace(item, points=tuple(move(p) for p in item.points), width=max(item.width * k, 1.5))
    if isinstance(item, Disc):
        return replace(item, center=move(item.center), radius=item.radius * k, width=item.width * k)
    return replace(item, at=move(item.at), size=max(round(item.size * k), 18))


def wrap(text: str, size: int, width: float) -> list[str]:
    """Coupe un texte en lignes qui tiennent dans `width` (largeur moyenne d'un caractère)."""
    per_line = max(int(width / (size * 0.55)), 8)
    lines: list[str] = []
    for word in text.split():
        if lines and len(lines[-1]) + 1 + len(word) <= per_line:
            lines[-1] += " " + word
        else:
            lines.append(word)
    return lines


def sheet(title: str, drawings: Sequence[Drawing], legend: Sequence[str] = ()) -> Drawing:
    """L'image de la leçon : chaque figure avec son nom et ce qu'il faut retenir (2 colonnes
    au-delà d'une figure), ou un schéma et sa légende numérotée."""
    drawings = list(drawings)[:4]
    columns = 1 if len(drawings) == 1 else 2
    cell_w = 1000 / columns
    k = min((cell_w - 40) / max(d.width for d in drawings), 1.2 if columns == 1 else 0.75)
    items: list[Item] = [Label(title, (500, 50), size=44, bold=True)]
    y = 110.0
    for row in range(0, len(drawings), columns):
        row_items = drawings[row : row + columns]
        figure_h = max(d.height for d in row_items) * k
        text_h = 0.0
        for col, d in enumerate(row_items):
            x0 = col * cell_w + (cell_w - d.width * k) / 2
            items += [_shift(item, x0, y, k) for item in d.items]
            cx, ty = col * cell_w + cell_w / 2, y + figure_h + 34
            if len(drawings) > 1:
                items.append(Label(d.name, (cx, ty), size=32, bold=True, color=BLUE))
                ty += 44
            for fact in d.facts:
                for line in wrap(fact, 26, cell_w - 50):
                    items.append(Label(line, (cx, ty), size=26))
                    ty += 34
            text_h = max(text_h, ty - (y + figure_h))
        y += figure_h + text_h + 30
    for line in legend:
        items.append(Label(line, (500, y), size=28))
        y += 38
    names = ", ".join(d.name.lower() for d in drawings)
    return Drawing(
        "fiche:" + "+".join(d.key for d in drawings),
        title,
        (),
        f"Fiche à retenir : {names}." if len(drawings) > 1 else drawings[0].alt,
        1000,
        y + 10,
        tuple(items),
    )


# --------------------------------------------------------------------------- #
# Schémas de la bibliothèque de figures (étape 22)
# --------------------------------------------------------------------------- #


def _rings(shapes: Any) -> list[list[Point]]:
    rings: list[list[Point]] = []
    for polygon in shapes:
        for ring in polygon:
            rings.append([(ring[i], ring[i + 1]) for i in range(0, len(ring) - 1, 2)])
    return rings


def _centroid(ring: Sequence[Point]) -> Point:
    """Centre de gravité d'un polygone (moyenne des sommets s'il est plat)."""
    area = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, [*ring[1:], ring[0]], strict=True):
        cross = x1 * y2 - x2 * y1
        area += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if abs(area) < 1e-6:
        return (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring))
    return (cx / (3 * area), cy / (3 * area))


def _ring_area(ring: Sequence[Point]) -> float:
    return (
        abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, [*ring[1:], ring[0]], strict=True))) / 2
    )


def _inside(p: Point, ring: Sequence[Point]) -> bool:
    """Le point est-il dans le polygone (règle du nombre de croisements) ?"""
    x, y = p
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, [*ring[1:], ring[0]], strict=True):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


MARK_RADIUS = 22.0
# Couleurs des zones de la leçon qui n'ont pas la leur (les régions d'une carte).
PALETTE = ("#f4a259", "#8cb369", "#5b8ec9", "#e07a8f", "#f2c14e", "#9b7ede", "#4fb3a9", "#d9895b")


def _mark_spot(
    ring: Sequence[Point], line: bool, taken: Sequence[Point], others: Sequence[Sequence[Point]] = ()
) -> Point:
    """Où écrire le numéro d'une zone : au centre, sinon le plus près du centre, dans la zone,
    sans toucher un autre numéro ni tomber sur une autre zone en couleur (la cheminée dans le
    cône)."""
    start = ring[len(ring) // 2] if line else _centroid(ring)
    candidates = [start]
    if line:
        candidates += [ring[i] for i in range(0, len(ring), max(len(ring) // 12, 1))]
    else:
        for radius in range(30, 330, 30):
            candidates += [
                (start[0] + radius * math.cos(a * math.pi / 8), start[1] + radius * math.sin(a * math.pi / 8))
                for a in range(16)
            ]
    for spot in candidates:
        if (
            (line or _inside(spot, ring))
            and all(math.dist(spot, t) > 2.4 * MARK_RADIUS for t in taken)
            and not any(_inside(spot, other) for other in others)
        ):
            return spot
    return start


def _lighter(color: str | None, amount: float = 0.6) -> str:
    """La couleur mélangée de blanc : une zone dont la leçon ne parle pas."""
    if not color or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        return GREY
    rgb = [int(color[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(c + (255 - c) * amount):02x}" for c in rgb)


def figure_drawing(figure: dict[str, Any], zone_ids: Sequence[str], numbered: bool = True) -> Drawing:
    """Un schéma de la bibliothèque : les zones `zone_ids` en couleur (numérotées si `numbered`),
    les autres pâlies ; le décor (mer, ciel, sol) reste. Sans nom écrit sur l'image."""
    wanted = list(dict.fromkeys(zone_ids))
    items: list[Item] = []
    for decor in figure.get("decor", []):
        for ring in _rings(decor["shapes"]):
            closed = decor.get("kind") != "line"
            items.append(
                Stroke(
                    tuple(ring),
                    closed=closed,
                    fill=decor.get("fill") if closed else None,
                    color=decor.get("stroke") or decor.get("fill") or GREY,
                    width=1 if closed else 3,
                )
            )
    zones = {z["id"]: z for z in figure["zones"]}
    for zone in figure["zones"]:
        on = zone["id"] in wanted
        own = zone.get("fill") or (PALETTE[wanted.index(zone["id"]) % len(PALETTE)] if on else None)
        fill = own if on else _lighter(own)
        for ring in _rings(zone["shapes"]):
            if zone["kind"] == "line":
                items.append(Stroke(tuple(ring), closed=False, color=fill or BLUE, width=6 if on else 3))
            else:
                items.append(Stroke(tuple(ring), fill=fill, color=INK if on else "#ffffff", width=1.5))
    marks: list[Item] = []
    taken: list[Point] = []
    for number, zone_id in enumerate(wanted, start=1):
        zone = zones.get(zone_id)
        if zone is None or not numbered:
            continue
        biggest = max(_rings(zone["shapes"]), key=_ring_area)
        others = [
            max(_rings(zones[o]["shapes"]), key=_ring_area)
            for o in wanted
            if o != zone_id
            and o in zones
            and zones[o]["kind"] != "line"
            and _ring_area(max(_rings(zones[o]["shapes"]), key=_ring_area)) < _ring_area(biggest)
        ]
        at = _mark_spot(biggest, zone["kind"] == "line", taken, others)
        taken.append(at)
        marks += [
            Disc(at, MARK_RADIUS, fill="#ffffff", color=INK, width=3),
            Label(str(number), at, size=26, bold=True),
        ]
    names = [zones[z]["name"] for z in wanted if z in zones]
    return Drawing(
        f"figure:{figure['id']}",
        figure["title"],
        (),
        f"{figure['title']} : {', '.join(names)} en couleur." if names else figure["title"],
        float(figure["width"]),
        float(figure["height"]),
        tuple(items + marks),
    )


def figure_sheet(figure: dict[str, Any], zone_ids: Sequence[str], title: str) -> Drawing:
    """L'image de la leçon : le schéma, les zones de la leçon numérotées, et leur légende."""
    zones = {z["id"]: z for z in figure["zones"]}
    wanted = [z for z in dict.fromkeys(zone_ids) if z in zones]
    drawing = figure_drawing(figure, wanted)
    legend = [
        f"{n}. {zones[z]['name'][:1].upper()}{zones[z]['name'][1:]}" for n, z in enumerate(wanted, start=1)
    ]
    sheet_drawing = sheet(title, [replace(drawing, name=title)], legend)
    return replace(
        sheet_drawing,
        alt=f"{figure['title']}, avec la légende : {', '.join(zones[z]['name'] for z in wanted)}.",
    )


# --------------------------------------------------------------------------- #
# Ce que le code dessine pour une leçon
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Planned:
    """Un dessin du code : une ou plusieurs figures de géométrie, ou un schéma et ses zones."""

    shapes: tuple[Shape, ...] = ()
    figure: str | None = None  # identifiant dans la bibliothèque de figures
    zones: tuple[str, ...] = ()


@dataclass(frozen=True)
class DrawingPlan:
    cover: Planned | None  # l'image de la leçon (fiche mémo)
    pictures: dict[str, Planned]  # notion (N1, N2…) → son image, sans nom écrit


MIN_FIGURE_ZONES = 2  # une seule zone : la leçon parle d'autre chose (« la Loire » dans un récit)


def plan_drawings(
    subject: str | None,
    title: str | None,
    notions: Sequence[tuple[str, str, str]],
    library: "FigureLibrary",
) -> DrawingPlan:
    """Ce que le code sait dessiner exactement pour cette leçon : les figures de géométrie d'une
    leçon de mathématiques (une par notion, la même figure une seule fois), sinon les zones d'un
    schéma de la bibliothèque nommées par les notions. `notions` : (référence, nom, phrase)."""
    pictures: dict[str, Planned] = {}
    if subject == "math":
        seen: set[str] = set()
        for ref, label, statement in notions:
            shape = find_shape(label) or find_shape(statement)
            if shape is not None and shape.key not in seen:
                seen.add(shape.key)
                pictures[ref] = Planned(shapes=(shape,))
        shapes = tuple(p.shapes[0] for p in pictures.values())
        if not shapes and title and (shape := find_shape(title)) is not None:
            shapes = (shape,)
        return DrawingPlan(Planned(shapes=shapes[:4]) if shapes else None, pictures)

    best: tuple[str, list[tuple[str, str]]] | None = None
    for figure in library.figures:
        if subject and figure.subject != subject:
            continue
        found: list[tuple[str, str]] = []
        for ref, label, _ in notions:
            zone = figure.find(label)
            if zone is not None and zone.id not in {z for _, z in found}:
                found.append((ref, zone.id))
        if found and (best is None or len(found) > len(best[1])):
            best = (figure.id, found)
    if best is None:
        return DrawingPlan(None, {})
    figure_id, found = best
    chosen = library.get(figure_id)
    title_match = chosen is not None and bool(title) and normalize(title or "") == normalize(chosen.title)
    if len(found) < MIN_FIGURE_ZONES and not title_match:
        return DrawingPlan(None, {})
    pictures = {ref: Planned(figure=figure_id, zones=(zone,)) for ref, zone in found}
    return DrawingPlan(Planned(figure=figure_id, zones=tuple(z for _, z in found)), pictures)


def draw_planned(
    planned: Planned, figure_data: dict[str, Any] | None, title: str, for_cover: bool, variant: int = 0
) -> Drawing:
    """Le dessin prévu : fiche mémo pour l'image de la leçon, figure seule pour une notion."""
    if planned.shapes:
        drawings = [shape_drawing(s, variant) for s in planned.shapes]
        return sheet(title if len(drawings) > 1 else drawings[0].name, drawings) if for_cover else drawings[0]
    assert figure_data is not None
    if for_cover:
        return figure_sheet(figure_data, planned.zones, title)
    return figure_drawing(figure_data, planned.zones, numbered=False)
