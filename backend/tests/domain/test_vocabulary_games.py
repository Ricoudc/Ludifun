"""§5.57 : jeux tirés des vraies leçons de CE1 — « Trouve le bon pronom », « Relie les
synonymes », « Le mot de la même famille ». Les réponses viennent de banques écrites à la main ;
les tests les recontrôlent indépendamment du code des jeux."""

import random

import pytest

from app.domain.activities.base import ActivityCode, InvalidResponse
from app.domain.activities.registry import ActivityRegistry
from app.domain.french import SYNONYMS, WORD_FAMILIES, Tense, conjugate
from app.domain.knowledge import (
    Grade,
    KnowledgeItem,
    KnowledgeMaterial,
    KnowledgeType,
    KnowledgeUnit,
    Subject,
)
from app.domain.mistakes import describe
from app.domain.simulated_pupil import respond

C = ActivityCode


def unit(label: str, statement: str = "", subject: Subject = Subject.FRENCH) -> KnowledgeUnit:
    item = KnowledgeItem(
        id="k1",
        type=KnowledgeType.FACT,
        label=label,
        statement=statement or f"{label}.",
        importance=4,
        source_excerpt=label,
    )
    material = KnowledgeMaterial(knowledge_id="k1", explanation="Relis la leçon.")
    return KnowledgeUnit(item=item, material=material, subject=subject, grade=Grade.CE1)


def test_banks_are_consistent() -> None:
    words = [w for pair in SYNONYMS for w in pair]
    assert len(words) == len(set(words))  # un mot n'a qu'une paire : une seule bonne réponse
    # Les paires des vraies leçons de CE1 y sont.
    assert {("gommer", "effacer"), ("bateau", "navire"), ("forêt", "bois")} <= set(SYNONYMS)
    family_words = [w for f in WORD_FAMILIES for w in (*f.words, f.trap)]
    assert len(family_words) == len(set(family_words))
    assert all(len(f.words) >= 3 and f.trap not in f.words for f in WORD_FAMILIES)


def test_which_lessons_get_which_game(registry: ActivityRegistry) -> None:
    pronoun, synonyms, family = registry.get(C.PRONOUN), registry.get(C.SYNONYMS), registry.get(C.WORD_FAMILY)
    assert pronoun.accepts(unit("Le verbe aller au présent"))
    assert not pronoun.accepts(unit("Le verbe partir au présent"))  # verbe inconnu du code
    assert synonyms.accepts(unit("Les synonymes"))
    assert family.accepts(unit("Les mots de la même famille"))
    assert not synonyms.accepts(unit("Les synonymes", subject=Subject.MATH))
    assert not family.accepts(unit("La famille de Louis XVI", subject=Subject.FRENCH))
    assert not synonyms.accepts(unit("Le verbe aller au présent"))


@pytest.mark.parametrize("seed", range(15))
def test_find_the_pronoun(registry: ActivityRegistry, seed: int) -> None:
    """Fiche « Trouve le bon pronom » : « ___ allons dormir » → nous. Les formes à deux pronoms
    possibles (« dis » : je ou tu) ne sont jamais demandées."""
    game = registry.get(C.PRONOUN)
    for label, verb in (("Le verbe aller au présent", "aller"), ("Le verbe dire au présent", "dire")):
        for difficulty in (1, 2, 3):
            activity = game.build([unit(label)], difficulty, random.Random(seed))
            forms = conjugate(verb, Tense.PRESENT)
            assert forms is not None and activity.payload["blank_first"]
            for row in activity.payload["items"]:
                assert forms.count(row["text"]) == 1  # une seule bonne réponse
                person = forms.index(row["text"])
                who = activity.solution["expected"][row["id"]]
                assert who == ("je", "tu", "il", "nous", "vous", "ils")[person]
            chips = [c["text"] for c in activity.payload["choices"]]
            # Au moins un intrus, sauf quand les six personnes sont demandées.
            assert len(chips) > len(activity.payload["items"]) or len(chips) == 6
            assert game.grade(activity, respond(activity, lambda _: True)).score == 1
            assert game.grade(activity, respond(activity, lambda _: False)).score < 1
    assert "dis" not in [
        r["text"]
        for r in game.build([unit("Le verbe dire au présent")], 3, random.Random(seed)).payload["items"]
    ]


@pytest.mark.parametrize("seed", range(15))
def test_link_the_synonyms(registry: ActivityRegistry, seed: int) -> None:
    """Fiche « Relie les mots synonymes » : les paires nommées par la leçon passent d'abord."""
    game = registry.get(C.SYNONYMS)
    lesson = unit("Les synonymes", "gommer et effacer, drôle et amusant, bus et car, bateau et navire.")
    for difficulty in (1, 2, 3):
        activity = game.build([lesson], difficulty, random.Random(seed))
        lefts = {i["id"]: i["text"] for i in activity.payload["left"]}
        rights = {i["id"]: i["text"] for i in activity.payload["right"]}
        assert len(lefts) == len(rights) == {1: 3, 2: 4, 3: 5}[difficulty]
        bank = {frozenset(p) for p in SYNONYMS}
        for left, right in activity.solution["pairs"].items():
            assert frozenset((lefts[left], rights[right])) in bank
        shown = {*lefts.values(), *rights.values()}
        lesson_pairs = [{"gommer", "effacer"}, {"drôle", "amusant"}, {"bus", "car"}, {"bateau", "navire"}]
        assert sum(p <= shown for p in lesson_pairs) == min(4, len(lefts))
        assert game.grade(activity, respond(activity, lambda _: True)).score == 1
        wrong = game.grade(activity, respond(activity, lambda _: False))
        assert 0 < wrong.score < 1
        mistake = describe(registry, activity, respond(activity, lambda _: False))
        assert mistake is not None and "→" in mistake.given
    with pytest.raises(InvalidResponse):
        game.grade(activity, {"pairs": [["l9", "r1"]]})


@pytest.mark.parametrize("seed", range(15))
def test_word_of_the_same_family(registry: ActivityRegistry, seed: int) -> None:
    """Fiche « Trouve un mot de la même famille » : la bonne réponse est de la famille du mot
    montré, les autres choix n'en sont pas ; aux difficultés 2 et 3, le piège qui lui ressemble."""
    game = registry.get(C.WORD_FAMILY)
    lesson = unit(
        "Les mots de la même famille", "nageur, nageuse, nageoire : nage. dentiste, dentifrice : dent."
    )
    family_of = {w: f for f in WORD_FAMILIES for w in f.words}
    for difficulty in (1, 2, 3):
        activity = game.build([lesson], difficulty, random.Random(seed))
        items = activity.payload["items"]
        assert len(items) == {1: 3, 2: 4, 3: 5}[difficulty]
        for item in items:
            shown = item["text"].split("»")[0].strip("« ")
            family = family_of[shown]
            answer = activity.solution["expected"][item["id"]]
            assert answer in family.words and answer != shown and answer in item["choices"]
            others = [c for c in item["choices"] if c != answer]
            assert len(others) == 3 and not set(others) & set(family.words)
            assert (family.trap in others) == (difficulty >= 2)
        # Les familles de la leçon d'abord : nage et dent.
        firsts = {family_of[i["text"].split("»")[0].strip("« ")].words[0] for i in items[:2]}
        assert firsts == {"nage", "dent"}
        assert game.grade(activity, respond(activity, lambda _: True)).score == 1
        assert game.grade(activity, respond(activity, lambda _: False)).score == 0
