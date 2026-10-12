"""Mesurer à la règle, symétrie, syllabes : la réponse est recalculée ici, indépendamment des
jeux (règle relue graduation par graduation, figure retournée à la main, syllabes de la banque
recomptées lettre par lettre)."""

import random
import re

import pytest

from app.domain.activities.base import ActivityCode, InvalidResponse
from app.domain.activities.registry import ActivityRegistry
from app.domain.french import SYLLABLE_WORDS
from app.domain.knowledge import Grade, KnowledgeUnit, Subject, Theme
from app.domain.math_generator import Topic, topics
from app.domain.mistakes import describe
from app.domain.simulated_pupil import respond
from tests.domain.test_math_games import unit as math_unit
from tests.domain.test_word_games import unit as french_unit

C = ActivityCode


def millimetres(text: str) -> int:
    """« 7 cm » → 70 ; « 5 cm 3 mm » → 53 ; « 8 mm » → 8."""
    found = re.fullmatch(r"(?:(\d+) cm)?(?: ?(\d+) mm)?", text)
    assert found and (found[1] or found[2]), text
    return int(found[1] or 0) * 10 + int(found[2] or 0)


def test_offered_by_topic(registry: ActivityRegistry) -> None:
    assert registry.get(C.RULER).accepts(math_unit("Mesurer des longueurs", Grade.CE1))
    assert registry.get(C.SYMMETRY).accepts(math_unit("La symétrie axiale", Grade.CE2))
    assert registry.get(C.SYLLABLES).accepts(french_unit("Les syllabes", grade=Grade.CP))
    assert not registry.get(C.RULER).accepts(math_unit("Les fractions"))
    assert not registry.get(C.SYMMETRY).accepts(math_unit("La symétrie", subject=Subject.SCIENCE))
    assert not registry.get(C.SYLLABLES).accepts(french_unit("Les syllabes", subject=Subject.MATH))


def test_a_drawn_game_is_not_crowded_out_by_computed_topics() -> None:
    """« Unités » et « comparer » donnent deux thèmes de calcul : la règle reste proposée."""
    notion = math_unit("Mesurer et comparer des longueurs ; les unités de longueur", Grade.CE2)
    found = topics(notion.item, Grade.CE2)
    assert Topic.LENGTH in found
    assert len([t for t in found if t not in (Topic.LENGTH, Topic.SYMMETRY)]) <= 2


@pytest.mark.parametrize("seed", range(40))
def test_the_ruler_is_read_right(registry: ActivityRegistry, seed: int) -> None:
    game = registry.get(C.RULER)
    for grade in (Grade.CP, Grade.CM1):
        for difficulty in (1, 2, 3):
            notion = math_unit("Mesurer des longueurs", grade)
            activity = game.build([notion], difficulty, random.Random(seed))
            payload = activity.payload
            start, length = payload["start_mm"], payload["length_mm"]
            assert start + length <= payload["ruler_cm"] * 10
            assert (start == 0) == (difficulty == 1)
            with_mm = difficulty == 3 and grade == Grade.CM1
            assert (length % 10 != 0) == with_mm
            choices = {c["id"]: c["text"] for c in payload["choices"]}
            assert len(set(choices.values())) == 4
            assert millimetres(choices[activity.solution["choice_id"]]) == length
            assert all(
                millimetres(t) != length for i, t in choices.items() if i != activity.solution["choice_id"]
            )
            if start:  # lire le nombre au bout de la règle est reconnu comme une erreur de lecture
                end = next((i for i, t in choices.items() if millimetres(t) == start + length), None)
                if end is not None:
                    assert activity.solution["misconceptions"][end] == "reading"


@pytest.mark.parametrize("seed", range(40))
def test_symmetry_is_mirrored_right(registry: ActivityRegistry, seed: int) -> None:
    game = registry.get(C.SYMMETRY)
    for difficulty in (1, 2, 3):
        activity = game.build([math_unit("La symétrie", Grade.CE2)], difficulty, random.Random(seed))
        p = activity.payload
        width, height, vertical = p["width"], p["height"], p["axis"] == "vertical"
        assert vertical == (difficulty < 3)
        filled = {tuple(c) for c in p["filled"]}
        # La figure est d'un seul côté, d'un seul tenant, à la bonne taille.
        assert all((x < width // 2) if vertical else (y < height // 2) for x, y in filled)
        assert len(filled) in {1: (3, 4), 2: (5, 6, 7), 3: (6, 7, 8)}[difficulty]
        seen, todo = set(), [next(iter(filled))]
        while todo:
            x, y = todo.pop()
            if (x, y) in filled and (x, y) not in seen:
                seen.add((x, y))
                todo += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
        assert seen == filled
        if difficulty < 3:  # la figure touche l'axe
            assert any(x == width // 2 - 1 for x, _ in filled)
        mirrored = {(width - 1 - x, y) if vertical else (x, height - 1 - y) for x, y in filled}
        assert game.grade(activity, {"selected": sorted(mirrored)}).score == 1
        slid = {(x + width // 2, y) if vertical else (x, y + height // 2) for x, y in filled}
        assert slid != mirrored
        result = game.grade(activity, {"selected": sorted(slid)})
        assert result.score == 0 and result.explanation and "glisser" in result.explanation
        missing_one = sorted(mirrored)[1:]
        assert 0 < game.grade(activity, {"selected": missing_one}).score <= 0.75
        with pytest.raises(InvalidResponse):  # une case du côté déjà dessiné
            game.grade(activity, {"selected": [[0, 0]]})


def test_every_syllable_word_is_well_cut() -> None:
    vowels = set("aeiouyéèêëàâîïôûù")
    words = [w for level in SYLLABLE_WORDS.values() for w in level]
    assert len({"".join(w) for w in words}) == len(words)  # pas deux fois le même mot
    for word in words:
        for syllable in word:
            assert vowels & set(syllable), word  # chaque syllabe a une voyelle
        joined = "".join(word)
        assert not joined.endswith("e") and not re.search(r"([bcdfgklmnprst])\1", joined), word
    assert all(len(w) == 2 for w in SYLLABLE_WORDS[1])
    assert all(len(w) == 3 for w in SYLLABLE_WORDS[2])


@pytest.mark.parametrize("seed", range(20))
def test_syllables_game(registry: ActivityRegistry, seed: int) -> None:
    game = registry.get(C.SYLLABLES)
    bank = {"".join(w): w for level in SYLLABLE_WORDS.values() for w in level}
    for difficulty in (1, 2, 3):
        activity = game.build([french_unit("Les syllabes", grade=Grade.CP)], difficulty, random.Random(seed))
        items = activity.payload["items"]
        assert len(items) == 3 and all(bank[i["text"]] in SYLLABLE_WORDS[difficulty] for i in items)
        answers = []
        for item in items:  # coupures recomptées lettre par lettre
            cuts, position = [], 0
            for syllable in bank[item["text"]][:-1]:
                position += len(syllable)
                cuts.append(position)
            answers.append([item["id"], cuts])
        assert game.grade(activity, {"answers": answers}).score == 1
        one_wrong = [answers[0], answers[1], [answers[2][0], []]]
        result = game.grade(activity, {"answers": one_wrong})
        assert 0 < result.score < 1 and [d["correct"] for d in result.details] == [True, True, False]
        assert result.details[2]["expected"] == "-".join(bank[items[2]["text"]])
    with pytest.raises(InvalidResponse):
        game.grade(activity, {"answers": [[items[0]["id"], [0]]]})  # coupure avant la première lettre
    with pytest.raises(InvalidResponse):
        game.grade(activity, {"answers": [["w9", [1]]]})


@pytest.mark.parametrize(
    ("code", "notion", "theme"),
    [
        (C.RULER, math_unit("Le trait", Grade.CE1), Theme.LENGTHS),
        (C.SYMMETRY, math_unit("Le papillon plié", Grade.CE2), Theme.SYMMETRY),
        (C.SYLLABLES, french_unit("Taper dans les mains"), Theme.SYLLABLES),
    ],
)
def test_the_theme_triggers_the_game(
    registry: ActivityRegistry, code: ActivityCode, notion: KnowledgeUnit, theme: Theme
) -> None:
    game = registry.get(code)
    assert not game.accepts(notion)
    with_theme = notion.model_copy(update={"item": notion.item.model_copy(update={"theme": theme})})
    assert game.accepts(with_theme)


@pytest.mark.parametrize("code", [C.RULER, C.SYMMETRY, C.SYLLABLES])
def test_parent_view_and_simulated_pupil(registry: ActivityRegistry, code: ActivityCode) -> None:
    notion = {
        C.RULER: math_unit("Mesurer des longueurs", Grade.CM1),
        C.SYMMETRY: math_unit("La symétrie", Grade.CM1),
        C.SYLLABLES: french_unit("Les syllabes", grade=Grade.CP),
    }[code]
    game = registry.get(code)
    for difficulty in sorted(game.difficulties):
        activity = game.build([notion], difficulty, random.Random(difficulty))
        assert game.grade(activity, respond(activity, lambda _: True)).score == 1
        wrong = respond(activity, lambda _: False)
        assert game.grade(activity, wrong).score < 1
        mistake = describe(registry, activity, wrong)
        assert mistake is not None and mistake.given and mistake.expected and "{" not in mistake.given
