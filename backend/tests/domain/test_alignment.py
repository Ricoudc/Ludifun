"""« Points alignés » : figures dessinées par le code, correction vérifiée ici par un calcul
indépendant (produit en croix) sur beaucoup de figures."""

import math
import random
from datetime import UTC, datetime
from itertools import combinations

import pytest

from app.domain import geometry
from app.domain.activities.base import ActivityCode, InvalidResponse
from app.domain.activities.registry import ActivityRegistry
from app.domain.composer import SessionComposer
from app.domain.knowledge import KnowledgeItem, KnowledgeMaterial, KnowledgeUnit, Subject
from app.domain.mistakes import describe
from app.domain.simulated_pupil import respond


def unit(
    label: str = "Repérer des alignements", subject: Subject | None = Subject.MATH, key: str = "k1"
) -> KnowledgeUnit:
    item = KnowledgeItem(
        id=key,
        type="rule",
        label=label,
        statement=f"{label}.",
        importance=4,
        attributes={"statement": label, "example": label},
        source_excerpt=label,
    )
    material = KnowledgeMaterial(knowledge_id=key, explanation="On vérifie avec la règle.")
    return KnowledgeUnit(item=item, material=material, subject=subject)


def spots(payload: dict[str, object]) -> dict[str, tuple[int, int]]:
    return {p["id"]: (p["x"], p["y"]) for p in payload["points"]}  # type: ignore[attr-defined]


def cross(a: tuple[int, int], b: tuple[int, int], c: tuple[int, int]) -> int:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def test_offered_for_a_math_alignment_notion_only(registry: ActivityRegistry) -> None:
    assert ActivityCode.ALIGN in registry.formats_for(unit())
    assert ActivityCode.ALIGN not in registry.formats_for(unit(subject=Subject.FRENCH))
    assert ActivityCode.ALIGN not in registry.formats_for(unit("Les fractions"))


@pytest.mark.parametrize("seed", range(60))
def test_the_answer_is_always_right(registry: ActivityRegistry, seed: int) -> None:
    game = registry.get(ActivityCode.ALIGN)
    # Oui / non : la réponse est celle du calcul.
    activity = game.build([unit()], 1, random.Random(seed))
    a, b, c = spots(activity.payload).values()
    assert activity.solution["choice_id"] == ("oui" if cross(a, b, c) == 0 else "non")
    if cross(a, b, c):
        assert geometry.distance_to_line(b, a, c) >= geometry.OFF_LINE  # ça se voit

    # Les 4 points alignés : exactement eux, et aucun autre trio aligné.
    activity = game.build([unit()], 2, random.Random(seed))
    points, expected = spots(activity.payload), activity.solution["expected"]
    assert len(points) == 7 and len(expected) == 4 and activity.payload["count"] == 4
    assert all(cross(*(points[i] for i in trio)) == 0 for trio in combinations(expected, 3))
    others = [trio for trio in combinations(points, 3) if not set(trio) <= set(expected)]
    assert all(cross(*(points[i] for i in trio)) != 0 for trio in others)

    # Avec les 2 points bleus : tous les points de leur droite, et seulement eux.
    activity = game.build([unit()], 3, random.Random(seed))
    points = spots(activity.payload)
    blue = [p["id"] for p in activity.payload["points"] if p["color"] == "blue"]
    on_line = {i for i in points if i not in blue and cross(points[blue[0]], points[blue[1]], points[i]) == 0}
    assert len(blue) == 2 and set(activity.solution["expected"]) == on_line and len(on_line) >= 2
    assert all(
        geometry.distance_to_line(points[i], points[blue[0]], points[blue[1]]) >= geometry.OFF_LINE
        for i in points
        if i not in on_line and i not in blue
    )
    # Deux points ne se touchent jamais sur l'écran.
    assert all(math.dist(p, q) >= geometry.MIN_GAP for p, q in combinations(points.values(), 2))


def test_grading(registry: ActivityRegistry) -> None:
    game = registry.get(ActivityCode.ALIGN)
    activity = game.build([unit()], 2, random.Random(4))
    expected = activity.solution["expected"]
    good = game.grade(activity, respond(activity, lambda _: True))
    assert good.score == 1 and good.correct_answer.startswith("Les points ")
    forgot_one = game.grade(activity, {"selected": expected[1:]})
    assert forgot_one.result == "partial" and forgot_one.errors
    stranger = next(p["id"] for p in activity.payload["points"] if p["id"] not in expected)
    assert game.grade(activity, {"selected": [*expected, stranger]}).score < 1
    with pytest.raises(InvalidResponse):
        game.grade(activity, {"selected": ["Z"]})

    yes_no = game.build([unit()], 1, random.Random(4))
    assert game.grade(yes_no, respond(yes_no, lambda _: True)).score == 1
    assert game.grade(yes_no, respond(yes_no, lambda _: False)).score == 0
    mistake = describe(registry, yes_no, respond(yes_no, lambda _: False))
    assert mistake is not None and mistake.question == "Les 3 points sont-ils alignés ?"
    wrong = describe(registry, activity, {"selected": expected[1:]})
    assert wrong is not None and wrong.given.startswith("Points touchés : ")


def test_a_geometry_lesson_plays_alignments(registry: ActivityRegistry) -> None:
    units = [unit(), unit("Tracer une droite passant par deux points alignés", key="k2")]
    composer = SessionComposer(registry)
    now = datetime(2026, 10, 9, 17, tzinfo=UTC)
    seen = {i.activity.type for seed in range(5) for i in composer.compose(units, {}, now, seed=seed).items}
    assert ActivityCode.ALIGN in seen
