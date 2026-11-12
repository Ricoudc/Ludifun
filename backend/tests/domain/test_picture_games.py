"""Étape 28 : apprendre par l'image. Les images des notions, validées par le parent, nourrissent
« Image et mot » et « Quelle image ? » ; sans elles, ces jeux n'existent pas. L'IA dit d'abord si
une image aide à retenir la leçon ; le code contrôle chaque proposition."""

import json
import random
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.activities.base import ActivityCode, InvalidResponse
from app.domain.activities.registry import ActivityRegistry
from app.domain.composer import SessionComposer
from app.domain.illustration import (
    NOT_NEEDED_DEFAULT,
    SINGLE_SUBJECT,
    ProposedPicture,
    Scene,
    build_prompt,
    plan_illustrations,
)
from app.domain.instructions import instruction
from app.domain.knowledge import KnowledgeUnit
from app.domain.mastery import Mastery
from app.domain.mistakes import describe
from app.domain.simulated_pupil import respond
from tests.domain.conftest import ReferenceLesson

GAMES = [(ActivityCode.PICTURE_MATCH, 1), (ActivityCode.PICTURE_FIND, 2)]


def pictured(units: list[KnowledgeUnit], count: int = 4) -> list[KnowledgeUnit]:
    """Les premières notions, avec une image validée chacune (adresse opaque)."""
    return [
        u.model_copy(update={"picture": f"/v1/lessons/L/images/{i}"}) for i, u in enumerate(units[:count])
    ]


@pytest.mark.parametrize(("code", "difficulty"), GAMES)
def test_picture_games_build_and_grade(
    history: ReferenceLesson, registry: ActivityRegistry, code: ActivityCode, difficulty: int
) -> None:
    units = pictured(list(history.units.values()))
    game = registry.get(code)
    activity = game.build(units, difficulty, random.Random(5))
    json.dumps([activity.payload, activity.solution])  # stockés en JSONB
    pictures = activity.payload["pictures"]
    assert len(pictures) == 4 and all(set(p) == {"id", "image"} for p in pictures)
    # Rien dans l'image envoyée ne donne la réponse : ni nom de notion ni identifiant.
    assert {p["image"] for p in pictures} == {u.picture for u in units}
    assert not any(u.id in json.dumps(activity.payload) for u in units)

    good = game.grade(activity, respond(activity, lambda _: True))
    assert good.score == 1 and set(good.evidence) == {u.id for u in units}
    bad = game.grade(activity, respond(activity, lambda _: False))
    assert bad.score == 0 and all(v == 0 for v in bad.evidence.values())
    half = game.grade(activity, respond(activity, lambda k: k in {units[0].id, units[1].id}))
    assert 0 < half.score < 1
    # La correction montre la bonne image, élément par élément.
    assert all(d["image"] in {u.picture for u in units} for d in bad.details)

    mistake = describe(registry, activity, respond(activity, lambda _: False))
    assert mistake is not None and mistake.given and mistake.expected
    assert "{" not in mistake.given + mistake.expected
    assert instruction(code, "CE1") and instruction(code, "4e")


def test_picture_match_relies_words_and_pictures(
    history: ReferenceLesson, registry: ActivityRegistry
) -> None:
    units = pictured(list(history.units.values()), 3)
    activity = registry.get(ActivityCode.PICTURE_MATCH).build(units, 1, random.Random(2))
    assert sorted(w["text"] for w in activity.payload["words"]) == sorted(u.item.label for u in units)
    with pytest.raises(InvalidResponse):  # une image, deux mots
        registry.get(ActivityCode.PICTURE_MATCH).grade(activity, {"pairs": [["p1", "w1"], ["p1", "w2"]]})
    with pytest.raises(InvalidResponse):
        registry.get(ActivityCode.PICTURE_MATCH).grade(activity, {"pairs": [["p9", "w1"]]})
    nothing = registry.get(ActivityCode.PICTURE_MATCH).grade(activity, {"pairs": []})
    assert nothing.score == 0


def test_picture_find_shows_the_sentence_to_remember(
    history: ReferenceLesson, registry: ActivityRegistry
) -> None:
    units = pictured(list(history.units.values()), 3)
    activity = registry.get(ActivityCode.PICTURE_FIND).build(units, 2, random.Random(2))
    assert sorted(c["text"] for c in activity.payload["clues"]) == sorted(u.item.statement for u in units)
    with pytest.raises(InvalidResponse):
        registry.get(ActivityCode.PICTURE_FIND).grade(activity, {"answers": [["c1", "p1"], ["c1", "p2"]]})


def test_without_three_validated_pictures_there_is_no_picture_game(
    history: ReferenceLesson, registry: ActivityRegistry
) -> None:
    units = list(history.units.values())
    for code, difficulty in GAMES:
        game = registry.get(code)
        assert not any(game.accepts(u) for u in units)  # aucune image validée
        assert not game.can_build(pictured(units, 2), difficulty)  # deux ne suffisent pas
        same = [u.model_copy(update={"picture": "/meme-image"}) for u in units[:3]]
        assert not game.can_build(same, difficulty)  # la même image deux fois : ambigu


def test_first_session_learns_with_the_pictures(history: ReferenceLesson, registry: ActivityRegistry) -> None:
    """Première séance : avec trois images validées, le jeu de fin est « Image et mot » ;
    ensuite, les deux jeux en images reviennent parmi les autres."""
    now = datetime(2026, 10, 8, 8, tzinfo=UTC)
    units = list(history.units.values())
    with_pictures = pictured(units, 4) + units[4:]
    composer = SessionComposer(registry)
    first = composer.compose(with_pictures, {}, now, seed=1)
    puzzle = next(i for i in first.items if i.block == "match")
    assert puzzle.activity.type is ActivityCode.PICTURE_MATCH
    without = composer.compose(units, {}, now, seed=1)
    assert all(i.activity.type not in {c for c, _ in GAMES} for i in without.items)
    due = {u.id: Mastery(60, 1, now - timedelta(days=1), now - timedelta(days=2)) for u in units}
    seen = {
        i.activity.type
        for seed in range(40)
        for i in composer.compose(with_pictures, due, now, seed=seed).items
    }
    assert {ActivityCode.PICTURE_MATCH, ActivityCode.PICTURE_FIND} <= seen


# --------------------------------------------------------------------------- #
# Une image aide-t-elle ? Le code contrôle la proposition de l'IA.
# --------------------------------------------------------------------------- #


def proposal(notion: str | None, scene: str = "A green caterpillar crawling on a leaf") -> ProposedPicture:
    return ProposedPicture(notion, scene, "Une chenille sur une feuille.")


def test_an_abstract_lesson_gets_no_image() -> None:
    plan = plan_illustrations(False, "Une règle de conjugaison ne se dessine pas.", None, None, [], ["N1"])
    assert plan.cover is None and not plan.cover_needed
    assert plan.cover_issue == "Une règle de conjugaison ne se dessine pas."
    assert plan_illustrations(False, None, None, None, [], ["N1"]).cover_issue == NOT_NEEDED_DEFAULT


def test_the_plan_keeps_valid_pictures_of_known_notions_only() -> None:
    plan = plan_illustrations(
        True,
        "On voit les animaux.",
        "A pond with frogs",
        "Une mare et des grenouilles.",
        [
            proposal("N1"),
            proposal("N1", "A butterfly"),  # deux fois la même notion : la première seule
            proposal("N9"),  # notion inconnue
            proposal(None),
            proposal("N2", 'A sign that says "frog"'),  # du texte dans l'image
            proposal("N3", "A blue whale"),
            proposal("N4", "A red fox"),
            proposal("N5", "A brown owl"),
            proposal("N6", "A small snail"),  # au-delà de la limite
        ],
        ["N1", "N2", "N3", "N4", "N5", "N6"],
        limit=4,
    )
    assert plan.cover == Scene("A pond with frogs", "Une mare et des grenouilles.") and plan.cover_needed
    assert list(plan.pictures) == ["N1", "N3", "N4", "N5"]
    assert plan.pictures["N1"].description == "A green caterpillar crawling on a leaf"
    assert set(plan.refused) == {"N2"} and "texte" in plan.refused["N2"]


def test_a_refused_cover_is_still_needed() -> None:
    plan = plan_illustrations(True, None, "A bloody battle", "Une bataille.", [], [])
    assert plan.cover is None and plan.cover_needed and "interdit" in plan.cover_issue


def test_a_notion_picture_shows_one_clear_subject() -> None:
    scene = Scene("A green caterpillar crawling on a leaf", "Une chenille.")
    assert SINGLE_SUBJECT in build_prompt(scene, "CE1", single_subject=True).prompt
    assert SINGLE_SUBJECT not in build_prompt(scene, "CE1").prompt
