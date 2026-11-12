"""Droite graduée, fraction à colorier, opération posée : la réponse est recalculée ici à partir de
ce que voit l'enfant (graduations écrites, parts, nombres posés), indépendamment du jeu."""

import random
from datetime import UTC, datetime
from fractions import Fraction

import pytest

from app.domain.activities.base import ActivityCode, BuiltActivity, InvalidResponse
from app.domain.activities.math_games import without_carry
from app.domain.activities.registry import ActivityRegistry
from app.domain.composer import SessionComposer
from app.domain.knowledge import Grade, KnowledgeUnit, Subject
from app.domain.mistakes import describe
from app.domain.simulated_pupil import respond
from tests.domain.test_alignment import unit as math_unit

C = ActivityCode
MATH_GAMES = {C.NUMBER_LINE, C.FRACTION_BAR, C.COLUMN_OP}


def unit(
    label: str, grade: Grade = Grade.CM1, subject: Subject = Subject.MATH, key: str = "k1"
) -> KnowledgeUnit:
    return math_unit(label, subject, key).model_copy(update={"grade": grade})


def number(text: str) -> Fraction:
    text = text.replace(" ", "").replace(" ", "").replace(",", ".")
    if "/" in text:
        top, bottom = text.split("/")
        return Fraction(int(top), int(bottom))
    return Fraction(text)


def value_at(activity: BuiltActivity, index: int) -> Fraction:
    """La valeur d'une graduation, déduite des deux premières graduations écrites."""
    (i, a), (j, b) = [(lab["index"], number(lab["text"])) for lab in activity.payload["labels"][:2]]
    found: Fraction = a + (b - a) / (j - i) * (index - i)
    return found


def test_offered_by_topic_and_grade(registry: ActivityRegistry) -> None:
    def games(label: str, grade: Grade = Grade.CM1, subject: Subject = Subject.MATH) -> set[ActivityCode]:
        return registry.formats_for(unit(label, grade, subject)) & MATH_GAMES

    assert games("Les fractions") == {C.NUMBER_LINE, C.FRACTION_BAR}
    assert games("Les nombres décimaux", Grade.CM2) == {C.NUMBER_LINE}
    assert games("L'addition posée", Grade.CE1) == {C.NUMBER_LINE, C.COLUMN_OP}
    assert games("La multiplication posée", Grade.CM1) == {C.COLUMN_OP}
    assert games("La multiplication posée", Grade.CE1) == set()  # posée à partir du CE2
    assert games("L'addition", Grade.CP) == {C.NUMBER_LINE}  # pas d'opération posée au CP
    assert games("Les fractions", subject=Subject.FRENCH) == set()
    assert games("Les volcans") == set()


@pytest.mark.parametrize("seed", range(40))
@pytest.mark.parametrize(
    ("label", "grade"),
    [("Les fractions", Grade.CM1), ("Les nombres décimaux", Grade.CM2), ("Comparer des nombres", Grade.CE1)],
)
def test_number_line_is_right(registry: ActivityRegistry, label: str, grade: Grade, seed: int) -> None:
    game = registry.get(C.NUMBER_LINE)
    placed = game.build([unit(label, grade)], 1 + seed % 2 * 2, random.Random(seed))  # placer
    target = placed.solution["index"]
    assert 0 < target < placed.payload["intervals"]
    assert value_at(placed, target) == number(placed.payload["prompt"].split("nombre ")[1].rstrip("."))
    read = game.build([unit(label, grade)], 2, random.Random(seed))  # lire
    chosen = {c["id"]: c["text"] for c in read.payload["choices"]}
    assert number(chosen[read.solution["choice_id"]]) == value_at(read, read.payload["arrow"])
    assert len(set(chosen.values())) == 4
    assert all(
        number(t) != value_at(read, read.payload["arrow"])
        for i, t in chosen.items()
        if i != read.solution["choice_id"]
    )


@pytest.mark.parametrize("seed", range(40))
def test_fraction_bar_is_right(registry: ActivityRegistry, seed: int) -> None:
    game = registry.get(C.FRACTION_BAR)
    for difficulty in (1, 3):
        activity = game.build([unit("Les fractions")], difficulty, random.Random(seed))
        asked = number(activity.payload["prompt"].split("les ")[1].split(" ")[0])
        assert Fraction(activity.solution["count"], activity.payload["parts"]) == asked
        good = list(range(activity.solution["count"]))
        assert game.grade(activity, {"colored": good[::-1]}).score == 1  # n'importe quelles parts
    read = game.build([unit("Les fractions")], 2, random.Random(seed))
    chosen = {c["id"]: c["text"] for c in read.payload["choices"]}
    shown = Fraction(len(read.payload["colored"]), read.payload["parts"])
    assert number(chosen[read.solution["choice_id"]]) == shown
    assert chosen[read.solution["choice_id"]] == f"{len(read.payload['colored'])}/{read.payload['parts']}"


@pytest.mark.parametrize("seed", range(40))
@pytest.mark.parametrize("grade", [Grade.CE1, Grade.CE2, Grade.CM1, Grade.CM2])
def test_column_operation_is_right(registry: ActivityRegistry, grade: Grade, seed: int) -> None:
    game = registry.get(C.COLUMN_OP)
    label = "L'addition, la soustraction et la multiplication posées"
    for difficulty in (1, 2, 3):
        activity = game.build([unit(label, grade)], difficulty, random.Random(seed * 3 + difficulty))
        a, b = map(int, activity.payload["operands"])
        operator = activity.payload["operator"]
        expected = {"+": a + b, "−": a - b, "×": a * b}[operator]
        assert int(activity.solution["result"]) == expected >= 0
        assert len(str(expected)) <= activity.payload["boxes"]
        if operator != "×":
            needs_carry = without_carry(a, b, operator) != expected
            assert needs_carry == (difficulty >= 2), (a, operator, b)
        if operator == "×":
            assert grade != Grade.CE1


def test_a_forgotten_carry_is_named(registry: ActivityRegistry) -> None:
    game = registry.get(C.COLUMN_OP)
    built = (game.build([unit("L'addition posée", Grade.CE2)], 2, random.Random(seed)) for seed in range(200))
    activity = next(candidate for candidate in built if candidate.payload["operator"] == "+")
    a, b = map(int, activity.payload["operands"])
    slip = game.grade(activity, {"result": str(without_carry(a, b, "+"))})
    assert slip.score == 0 and "retenues" in (slip.explanation or "")
    assert game.grade(activity, {"result": "0" + activity.solution["result"]}).score == 1  # zéro devant
    with pytest.raises(InvalidResponse):
        game.grade(activity, {"result": "12a"})


@pytest.mark.parametrize("code", sorted(MATH_GAMES))
def test_simulated_pupil_and_parent_view(registry: ActivityRegistry, code: ActivityCode) -> None:
    game = registry.get(code)
    label = {
        C.NUMBER_LINE: "Les fractions",
        C.FRACTION_BAR: "Les fractions",
        C.COLUMN_OP: "L'addition posée",
    }[code]
    for difficulty in sorted(game.difficulties):
        activity = game.build([unit(label)], difficulty, random.Random(difficulty))
        assert game.grade(activity, respond(activity, lambda _: True)).score == 1
        wrong = respond(activity, lambda _: False)
        assert game.grade(activity, wrong).score == 0
        mistake = describe(registry, activity, wrong)
        assert mistake is not None and mistake.given and mistake.expected


def test_a_math_session_mixes_the_games(registry: ActivityRegistry) -> None:
    units = [unit("Les fractions"), unit("Comparer des fractions", key="k2")]
    composer = SessionComposer(registry)
    now = datetime(2026, 10, 9, 17, tzinfo=UTC)
    seen = {i.activity.type for seed in range(6) for i in composer.compose(units, {}, now, seed=seed).items}
    assert {C.NUMBER_LINE, C.FRACTION_BAR} <= seen


def test_formats_played_lately_come_last(registry: ActivityRegistry) -> None:
    """Règle `vary_formats` (1.12.0) : à difficulté égale, le format le moins joué d'abord."""
    composer = SessionComposer(registry)
    fractions = unit("Les fractions")
    first = [code for code, _ in composer._options(fractions, (1,), None, {}, False, random.Random(1))]
    assert len(first) >= 2
    composer.played.update({first[0]: 5})
    again = [code for code, _ in composer._options(fractions, (1,), None, {}, False, random.Random(1))]
    assert again[0] != first[0] and again[-1] == first[0]
