"""§5.62 : « Le bon son » (ou, on, an, in, oi) et « Anglais en images ». Les banques sont
écrites à la main ; les tests recontrôlent leurs règles indépendamment du code des jeux."""

import random

import pytest

from app.domain.activities.base import ActivityCode
from app.domain.activities.registry import ActivityRegistry
from app.domain.english import ENGLISH_WORDS, EnglishTheme, english_themes, lesson_words
from app.domain.knowledge import (
    Grade,
    KnowledgeItem,
    KnowledgeMaterial,
    KnowledgeType,
    KnowledgeUnit,
    Subject,
)
from app.domain.mistakes import describe
from app.domain.phonics import GRAPHIES, SOUND_WORDS, SOUNDS, lesson_sounds, words_of
from app.domain.simulated_pupil import respond

C = ActivityCode
# Vrais mots qu'une mauvaise réponse ne doit jamais former (relevés en écrivant la banque).
REAL_WORDS = {
    "manche", "dont", "raison", "toute", "tante", "vont", "mou", "mon", "pou", "pan", "pin", "trou",
    "doit", "cochin", "citrin", "sapan", "lapon", "moi", "main", "bain", "bon", "son", "ton",
}  # fmt: skip


def unit(
    label: str, grade: Grade | None = Grade.CP, statement: str = "", subject: Subject | None = None
) -> KnowledgeUnit:
    if subject is None:
        subject = Subject.ENGLISH if label[:1].isascii() and "son" not in label.lower() else Subject.FRENCH
    item = KnowledgeItem(
        id="k1",
        type=KnowledgeType.FACT,
        label=label,
        statement=statement or f"{label}.",
        importance=4,
        source_excerpt=label,
    )
    material = KnowledgeMaterial(knowledge_id="k1", explanation="Relis la leçon.")
    return KnowledgeUnit(item=item, material=material, subject=subject, grade=grade)


def test_the_sound_bank_follows_its_rules() -> None:
    words = [w.word for w in SOUND_WORDS]
    assert len(words) == len(set(words))
    assert "mouche" not in words  # m__che → « manche »
    for w in SOUND_WORDS:
        assert w.sound in SOUNDS and w.graphy in GRAPHIES[w.sound] and w.graphy in w.word
        assert w.masked.count("__") == 1 and w.with_letters(w.graphy) == w.word
        # Les autres réponses du jeu ne forment pas un autre vrai mot.
        others = [g for g in GRAPHIES[w.sound] if g != w.graphy]
        if not w.graphies_only:
            others += [GRAPHIES[s][0] for s in SOUNDS if s != w.sound]
        assert not {w.with_letters(g) for g in others} & REAL_WORDS, w.word
    for sound in SOUNDS:  # assez de mots pour le niveau 2 (5 cartes)
        plain = [w for w in words_of(sound) if w.graphy == GRAPHIES[sound][0] and not w.graphies_only]
        assert len(plain) >= 5, sound


@pytest.mark.parametrize(
    ("text", "sounds"),
    [
        ("Le son [ou]", ["ou"]),
        ("Les sons an et en", ["an"]),
        ("J'entends on", ["on"]),
        ("Les sons on/an", ["on", "an"]),
        ("Le son in : lapin, main, peinture", ["in"]),
        ("Le sondage de la classe", []),
        ("Les sons de l'alphabet", []),
    ],
)
def test_which_sounds_a_lesson_studies(text: str, sounds: list[str]) -> None:
    assert lesson_sounds(text) == sounds


def test_who_gets_the_sound_game(registry: ActivityRegistry) -> None:
    game = registry.get(C.SOUNDS)
    assert game.accepts(unit("Le son ou")) and game.accepts(unit("Le son ou", grade=None))
    assert game.accepts(unit("Les sons an et en", grade=Grade.CE2))
    assert not game.accepts(unit("Le son ou", grade=Grade.CM1))
    assert not game.accepts(unit("Le son ou", subject=Subject.MATH))
    assert not game.accepts(unit("Les syllabes"))


@pytest.mark.parametrize("seed", range(10))
def test_the_right_sound(registry: ActivityRegistry, seed: int) -> None:
    """Chaque carte : une image, le mot à compléter, le mot lu à voix haute ; une seule
    réponse refait le mot entendu."""
    game = registry.get(C.SOUNDS)
    by_word = {w.word: w for w in SOUND_WORDS}
    for label, studied in (
        ("Le son ou", {"ou"}),
        ("Les sons an et en", {"an"}),
        ("Les sons on et an", {"on", "an"}),
    ):
        for difficulty in (1, 2, 3):
            activity = game.build([unit(label, statement=f"{label}.")], difficulty, random.Random(seed))
            items = activity.payload["items"]
            assert len(items) == {1: 4, 2: 5, 3: 5}[difficulty]
            sounds_seen = set()
            for item in items:
                word = by_word[item["say"]]
                answer = activity.solution["expected"][item["id"]]
                assert item["picture"] == word.picture and item["lang"] == "fr-FR"
                assert answer in item["choices"] and len(set(item["choices"])) == len(item["choices"])
                assert item["text"].replace("__", answer) == word.word
                assert all(item["text"].replace("__", c) != word.word for c in item["choices"] if c != answer)
                sounds_seen.add(word.sound)
                if difficulty < 3:
                    assert answer == GRAPHIES[word.sound][0]  # l'écriture simple d'abord
                    assert len(item["choices"]) == {1: 2, 2: 3}[difficulty]
            assert sounds_seen & studied  # les sons de la leçon
            if difficulty == 3 and studied & {"an", "on"}:
                for item in items:  # comment s'écrit le son
                    assert set(item["choices"]) == set(GRAPHIES[by_word[item["say"]].sound])
            assert game.grade(activity, respond(activity, lambda _: True)).score == 1
            assert game.grade(activity, respond(activity, lambda _: False)).score == 0


def test_a_wrong_sound_is_shown_to_the_parent(registry: ActivityRegistry) -> None:
    game = registry.get(C.SOUNDS)
    activity = game.build([unit("Le son ou")], 1, random.Random(1))
    mistake = describe(registry, activity, respond(activity, lambda _: False))
    assert mistake is not None
    first = activity.payload["items"][0]
    assert f"{first['picture']} {first['text']} →" in mistake.given
    assert first["say"] in mistake.expected


@pytest.mark.parametrize(
    ("text", "themes"),
    [
        ("Colours", [EnglishTheme.COLOURS]),
        ("Les couleurs en anglais", [EnglishTheme.COLOURS]),
        ("The days of the week", [EnglishTheme.DAYS]),
        ("My pets: a dog and a cat", [EnglishTheme.ANIMALS]),
        ("I like red and blue", [EnglishTheme.COLOURS]),  # deux mots de la banque
        ("Hello, my name is Tom", []),
    ],
)
def test_english_themes(text: str, themes: list[EnglishTheme]) -> None:
    assert english_themes(text) == themes


def test_the_english_bank() -> None:
    assert len({w.english for w in ENGLISH_WORDS}) == len(ENGLISH_WORDS)
    for theme in EnglishTheme:
        words = [w for w in ENGLISH_WORDS if w.theme == theme]
        assert len(words) >= 6, theme
        pictured = [w.picture for w in words if w.picture]
        assert len(pictured) == len(set(pictured))
        assert all(w.picture is None for w in words) or all(w.picture for w in words)
    assert [w.english for w in lesson_words("Colours: red, blue and green")] == ["red", "blue", "green"]


@pytest.mark.parametrize("seed", range(10))
def test_english_in_pictures(registry: ActivityRegistry, seed: int) -> None:
    game = registry.get(C.ENGLISH_WORDS)
    by_english = {w.english: w for w in ENGLISH_WORDS}
    for label in ("Colours: red, blue, green", "The days of the week", "Animals"):
        for difficulty in (1, 2, 3):
            activity = game.build([unit(label, grade=Grade.CE2)], difficulty, random.Random(seed))
            items = activity.payload["items"]
            assert len(items) == {1: 4, 2: 5, 3: 6}[difficulty]
            for item in items:
                answer = activity.solution["expected"][item["id"]]
                assert answer in item["choices"] and len(set(item["choices"])) == len(item["choices"])
                assert len(item["choices"]) == {1: 3, 2: 3, 3: 4}[difficulty]
                assert item["lang"] == "en-GB"
                word = next(
                    w
                    for w in ENGLISH_WORDS
                    if answer in (w.english, w.picture, w.french) and w.english in item.get("say", w.english)
                )
                if difficulty == 2:  # entendre le mot anglais, toucher l'image (ou le mot français)
                    assert item["say"] == word.english and answer == (word.picture or word.french)
                else:
                    assert answer in by_english and item["say"] == ", ".join(item["choices"])
                    if difficulty == 3 or by_english[answer].picture is None:
                        assert item["text"] == by_english[answer].french
                    else:
                        assert item["picture"] == by_english[answer].picture
            if label.startswith("Colours") and difficulty == 1:  # les mots de la leçon d'abord
                shown = {activity.solution["expected"][i["id"]] for i in items}
                assert {"red", "blue", "green"} <= shown
            assert game.grade(activity, respond(activity, lambda _: True)).score == 1
            assert game.grade(activity, respond(activity, lambda _: False)).score == 0
    assert not game.accepts(unit("Les couleurs", subject=Subject.FRENCH))
