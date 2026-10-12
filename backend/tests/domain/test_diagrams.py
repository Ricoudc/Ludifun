"""§5.61 : ce qui doit être exact est dessiné par le code — figures de géométrie avec leur
codage, schémas légendés de la bibliothèque. Les tests recalculent les propriétés des figures
(côtés égaux, angles droits) indépendamment du code qui les trace."""

import json
import math

import pytest

from app.domain.diagrams import (
    SHAPES,
    Disc,
    Label,
    Stroke,
    draw_planned,
    figure_drawing,
    figure_sheet,
    find_shape,
    plan_drawings,
    shape_drawing,
    sheet,
)
from app.domain.figures import default_library, figure_path


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("Le carré", "carre"),
        ("Les carrés et les rectangles", "carre"),
        ("Reconnaître un rectangle", "rectangle"),
        ("Le triangle rectangle", "triangle-rectangle"),
        ("Les triangles isocèles", "triangle-isocele"),
        ("Le triangle équilatéral", "triangle-equilateral"),
        ("Tracer un cercle au compas", "cercle"),
        ("Le losange", "losange"),
        ("Les droites perpendiculaires", "perpendiculaires"),
        ("Droites parallèles", "paralleles"),
        ("Segment, droite et demi-droite", "demi-droite"),
        ("L'angle droit", "angle-droit"),
        ("L'axe de symétrie", "symetrie"),
        ("Le pavé droit", "pave"),
        ("Calculer le périmètre", "perimetre"),
        ("je voudrais un carré", "carre"),  # remarque du parent
    ],
)
def test_the_shape_named_in_a_lesson(text: str, key: str) -> None:
    shape = find_shape(text)
    assert shape is not None and shape.key == key


@pytest.mark.parametrize(
    "text",
    [
        "Le mètre carré",
        "Les centimètres carrés",
        "Trois au carré",
        "Le mètre cube",
        "Placer un nombre sur la droite graduée",
        "Tourner à droite",
        "La ligne droite",
        "Les fractions",
        "L'axe chronologique",
    ],
)
def test_units_and_directions_are_not_shapes(text: str) -> None:
    assert find_shape(text) is None


def _sides(points: tuple[tuple[float, float], ...]) -> list[float]:
    return [math.dist(points[i], points[(i + 1) % len(points)]) for i in range(len(points))]


def _cos(points: tuple[tuple[float, float], ...], i: int) -> float:
    p, a, b = points[i], points[i - 1], points[(i + 1) % len(points)]
    u, v = (a[0] - p[0], a[1] - p[1]), (b[0] - p[0], b[1] - p[1])
    return (u[0] * v[0] + u[1] * v[1]) / (math.hypot(*u) * math.hypot(*v))


def _outline(key: str, variant: int = 0) -> tuple[tuple[float, float], ...]:
    shape = next(s for s in SHAPES if s.key == key)
    drawing = shape_drawing(shape, variant)
    return next(i for i in drawing.items if isinstance(i, Stroke) and i.closed and i.fill).points


def _accents(key: str) -> int:
    """Les traits du codage (petits traits, angles droits) : en couleur."""
    shape = next(s for s in SHAPES if s.key == key)
    return sum(1 for i in shape_drawing(shape).items if isinstance(i, Stroke) and i.color == "#e8552d")


@pytest.mark.parametrize("variant", [0, 1, 2])
def test_the_figures_are_exact(variant: int) -> None:
    square = _outline("carre", variant)
    assert max(_sides(square)) - min(_sides(square)) < 1e-6
    assert all(abs(_cos(square, i)) < 1e-9 for i in range(4))
    rectangle = _outline("rectangle", variant)
    a, b, c, d = _sides(rectangle)
    assert abs(a - c) < 1e-6 and abs(b - d) < 1e-6 and abs(a - b) > 50
    assert all(abs(_cos(rectangle, i)) < 1e-9 for i in range(4))
    rhombus = _outline("losange", variant)
    assert max(_sides(rhombus)) - min(_sides(rhombus)) < 1e-6 and abs(_cos(rhombus, 0)) > 0.1
    equilateral = _outline("triangle-equilateral", variant)
    assert max(_sides(equilateral)) - min(_sides(equilateral)) < 1e-6
    right = _outline("triangle-rectangle", variant)
    assert abs(_cos(right, 0)) < 1e-9
    isosceles = _outline("triangle-isocele", variant)
    sides = sorted(_sides(isosceles))
    assert abs(sides[1] - sides[2]) < 1e-6 and sides[2] - sides[0] > 10


def test_the_coding_of_the_notebook() -> None:
    """Carré : 4 petits traits + 4 angles droits ; rectangle : 6 traits (2 + 1 + 2 + 1) + 4."""
    assert _accents("carre") == 8
    assert _accents("rectangle") == 10
    assert _accents("triangle-equilateral") == 3
    assert _accents("triangle-rectangle") == 1
    circle = shape_drawing(find_shape("Le cercle"))  # type: ignore[arg-type]
    disc = next(i for i in circle.items if isinstance(i, Disc) and i.radius > 100)
    diameter = next(i for i in circle.items if isinstance(i, Stroke) and i.dashed)
    radius = next(i for i in circle.items if isinstance(i, Stroke) and i.color == "#e8552d")
    assert abs(math.dist(*diameter.points) - 2 * disc.radius) < 1e-6
    assert abs(math.dist(*radius.points) - disc.radius) < 1e-6


def test_the_picture_of_a_notion_does_not_give_the_answer() -> None:
    """Pour les jeux « apprendre par l'image » : aucun nom sur l'image, seulement les sommets."""
    for shape in SHAPES:
        texts = {i.text for i in shape_drawing(shape).items if isinstance(i, Label)}
        assert all(len(t) <= 5 for t in texts), (shape.key, texts)  # « A », « (d1) », « [AB) »
        assert shape.facts and shape.alt


def test_the_lesson_sheet_names_each_figure_and_what_to_remember() -> None:
    shapes = [find_shape(t) for t in ("Le carré", "Le rectangle", "Le losange")]
    drawing = sheet("Les quadrilatères", [shape_drawing(s) for s in shapes if s])
    texts = [i.text for i in drawing.items if isinstance(i, Label)]
    assert texts[0] == "Les quadrilatères"
    assert {"Le carré", "Le rectangle", "Le losange", "Il a 4 angles droits."} <= set(texts)
    assert drawing.width == 1000 and drawing.height > 600


def test_what_the_code_draws_for_a_lesson() -> None:
    library = default_library()
    plan = plan_drawings(
        "math",
        "Les quadrilatères",
        [
            ("N1", "Le carré", "Un carré a 4 côtés égaux et 4 angles droits."),
            ("N2", "Le rectangle", "Un rectangle a 4 angles droits."),
            ("N3", "Les carrés", "Encore le carré."),  # la même figure : une seule image
            ("N4", "Le mètre carré", "Une unité d'aire."),  # pas un carré : la grille de l'aire
            ("N5", "La propriété des diagonales", "Les diagonales du losange se coupent à angle droit."),
        ],
        library,
    )
    assert {r: p.shapes[0].key for r, p in plan.pictures.items()} == {
        "N1": "carre",
        "N2": "rectangle",
        "N4": "aire",
        "N5": "losange",
    }
    assert plan.cover is not None and [s.key for s in plan.cover.shapes] == [
        "carre",
        "rectangle",
        "aire",
        "losange",
    ]
    # En géographie, « les parallèles » ne sont pas des droites à tracer.
    assert (
        plan_drawings(
            "geography", None, [("N1", "Les parallèles", "Des cercles imaginaires.")], library
        ).cover
        is None
    )
    # Un schéma de la bibliothèque : les zones dont parle la leçon.
    volcano = plan_drawings(
        "science",
        "Les volcans",
        [("N1", "Le cratère", "…"), ("N2", "La cheminée", "…"), ("N3", "L'éruption", "…")],
        library,
    )
    assert volcano.cover is not None and volcano.cover.figure == "volcan"
    assert set(volcano.pictures) == {"N1", "N2"}
    # Une seule zone, sans que la leçon porte sur le schéma : rien.
    assert plan_drawings("geography", "Un récit", [("N1", "La Loire", "…")], library).cover is None


def test_the_schema_numbers_the_zones_of_the_lesson() -> None:
    path = figure_path("volcan")
    assert path is not None
    figure = json.loads(path.read_text(encoding="utf-8"))
    zones = ["cone-volcanique", "chambre-magmatique", "cheminee", "cratere"]
    drawing = figure_sheet(figure, zones, "Le volcan")
    texts = [i.text for i in drawing.items if isinstance(i, Label)]
    assert {"1", "2", "3", "4"} <= set(texts)
    assert "1. Cône volcanique" in texts and "4. Cratère" in texts
    marks = [i.center for i in drawing.items if isinstance(i, Disc)]
    assert len(marks) == 4
    assert all(math.dist(a, b) > 44 for i, a in enumerate(marks) for b in marks[i + 1 :])  # lisibles
    # L'image d'une notion : la zone en couleur, sans numéro ni nom.
    alone = figure_drawing(figure, ["cratere"], numbered=False)
    assert not [i for i in alone.items if isinstance(i, Label)]
    assert (
        draw_planned(
            plan_drawings("science", "Le volcan", [("N1", "Le cratère", "…")], default_library()).pictures[
                "N1"
            ],
            figure,
            "Le volcan",
            for_cover=False,
        )
        == alone
    )
