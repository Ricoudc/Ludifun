"""Lire l'heure, compter la monnaie, ranger des mots dans l'ordre alphabétique : la réponse est
recalculée ici, indépendamment des jeux."""

import random
import re

import pytest

from app.domain.activities.base import ActivityCode, InvalidResponse
from app.domain.activities.registry import ActivityRegistry
from app.domain.french import ALPHABET_WORDS
from app.domain.knowledge import Grade, Subject
from app.domain.mistakes import describe
from app.domain.simulated_pupil import respond
from app.domain.text import normalize
from tests.domain.test_math_games import unit as math_unit
from tests.domain.test_word_games import unit as french_unit

C = ActivityCode


def cents(text: str) -> int:
    """« 2,30 € » → 230 ; « 50 c » → 50 ; « 12 € » → 1200."""
    text = text.replace(" ", "").replace(" ", "")
    if text.endswith("c"):
        return int(text[:-1])
    euros, _, rest = text.removesuffix("€").partition(",")
    return int(euros) * 100 + int(rest or 0)


def test_offered_by_topic(registry: ActivityRegistry) -> None:
    assert registry.get(C.CLOCK).accepts(math_unit("Lire l'heure", Grade.CE1))
    assert registry.get(C.MONEY).accepts(math_unit("La monnaie : pièces et billets", Grade.CP))
    assert registry.get(C.ALPHA_ORDER).accepts(french_unit("L'ordre alphabétique"))
    assert not registry.get(C.CLOCK).accepts(math_unit("Les fractions"))
    assert not registry.get(C.ALPHA_ORDER).accepts(french_unit("L'ordre alphabétique", subject=Subject.MATH))


@pytest.mark.parametrize("seed", range(40))
def test_the_clock_is_read_right(registry: ActivityRegistry, seed: int) -> None:
    game = registry.get(C.CLOCK)
    for difficulty in (1, 2, 3):
        activity = game.build([math_unit("Lire l'heure", Grade.CE1)], difficulty, random.Random(seed))
        hour, minute = activity.payload["hour"], activity.payload["minute"]
        assert 1 <= hour <= 12 and minute % {1: 60, 2: 15, 3: 5}[difficulty] == 0
        choices = {c["id"]: c["text"] for c in activity.payload["choices"]}
        expected = f"{hour} h" if minute == 0 else f"{hour} h {minute:02d}"
        assert choices[activity.solution["choice_id"]] == expected
        assert len(set(choices.values())) == 4
        for text in choices.values():  # que des heures possibles
            found = re.fullmatch(r"(\d+) h(?: (\d\d))?", text)
            assert found and 1 <= int(found[1]) <= 12 and int(found[2] or 0) < 60


@pytest.mark.parametrize("seed", range(40))
def test_money_is_counted_right(registry: ActivityRegistry, seed: int) -> None:
    game = registry.get(C.MONEY)
    for grade in (Grade.CP, Grade.CM1):
        for difficulty in (1, 3):
            activity = game.build([math_unit("La monnaie", grade)], difficulty, random.Random(seed))
            total = sum(i["value"] for i in activity.payload["items"])
            choices = {c["id"]: c["text"] for c in activity.payload["choices"]}
            assert cents(choices[activity.solution["choice_id"]]) == total
            assert all(cents(t) != total for i, t in choices.items() if i != activity.solution["choice_id"])
            if difficulty == 1:
                assert all(i["value"] % 100 == 0 for i in activity.payload["items"])  # euros seulement
        pay = game.build([math_unit("La monnaie", grade)], 2, random.Random(seed))
        price = pay.solution["price"]
        assert price < sum(i["value"] for i in pay.payload["items"])
        assert game.grade(pay, respond(pay, lambda _: True)).score == 1  # payable juste
        everything = [i["id"] for i in pay.payload["items"]]
        assert game.grade(pay, {"selected": everything}).score == 0  # trop d'argent
        with pytest.raises(InvalidResponse):
            game.grade(pay, {"selected": ["m99"]})


@pytest.mark.parametrize("seed", range(40))
def test_alphabetical_order(registry: ActivityRegistry, seed: int) -> None:
    game = registry.get(C.ALPHA_ORDER)
    for difficulty in (1, 2, 3):
        activity = game.build(
            [french_unit("Ranger des mots dans l'ordre alphabétique")], difficulty, random.Random(seed)
        )
        texts = activity.solution["texts"]
        words = [texts[i] for i in activity.solution["order"]]
        plain = [normalize(w) for w in words]
        assert plain == sorted(plain) and len(set(plain)) == len(plain)
        starts = [p[: {1: 1, 2: 1, 3: 2}[difficulty]] for p in plain]
        assert (len(set(starts)) == len(starts)) == (difficulty == 1)
        assert [i["id"] for i in activity.payload["items"]] != activity.solution["order"]  # mélangé
        assert game.grade(activity, {"order": activity.solution["order"]}).score == 1


def test_alphabet_words_are_distinct_without_accents() -> None:
    plain = [normalize(w) for w in ALPHABET_WORDS]
    assert len(set(plain)) == len(plain) and all(" " not in w and "-" not in w for w in ALPHABET_WORDS)


@pytest.mark.parametrize("code", [C.CLOCK, C.MONEY, C.ALPHA_ORDER])
def test_parent_view_and_simulated_pupil(registry: ActivityRegistry, code: ActivityCode) -> None:
    notion = {
        C.CLOCK: math_unit("Lire l'heure", Grade.CE2),
        C.MONEY: math_unit("Rendre la monnaie", Grade.CE2),
        C.ALPHA_ORDER: french_unit("L'ordre alphabétique"),
    }[code]
    game = registry.get(code)
    for difficulty in sorted(game.difficulties):
        activity = game.build([notion], difficulty, random.Random(difficulty))
        assert game.grade(activity, respond(activity, lambda _: True)).score == 1
        wrong = respond(activity, lambda _: False)
        assert game.grade(activity, wrong).score < 1
        mistake = describe(registry, activity, wrong)
        assert mistake is not None and mistake.given and mistake.expected
