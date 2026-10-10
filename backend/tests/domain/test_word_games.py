"""Jeux calculés pour toutes les matières : chasse aux mots, conjugaison, homophones, frise. Les
réponses sont comparées à des tableaux écrits à la main, indépendants du code des jeux."""

import random

import pytest

from app.domain.activities.base import ActivityCode, InvalidResponse
from app.domain.activities.registry import ActivityRegistry
from app.domain.french import HOMOPHONES, LEXICON, Tense, conjugate, homophone_pairs, tense_of
from app.domain.knowledge import (
    Grade,
    KnowledgeItem,
    KnowledgeMaterial,
    KnowledgeType,
    KnowledgeUnit,
    Sorting,
    SortingBox,
    Subject,
)
from app.domain.mistakes import describe
from app.domain.simulated_pupil import respond
from tests.domain.conftest import load_lesson

C = ActivityCode
NEW_GAMES = (C.WORD_HUNT, C.CONJUGATION, C.HOMOPHONE)


def unit(
    label: str,
    subject: Subject = Subject.FRENCH,
    grade: Grade = Grade.CE2,
    sorting: Sorting | None = None,
    key: str = "k1",
) -> KnowledgeUnit:
    item = KnowledgeItem(
        id=key,
        type=KnowledgeType.RULE,
        label=label,
        statement=f"{label}.",
        importance=4,
        attributes={"statement": label, "example": label},
        source_excerpt=label,
    )
    material = KnowledgeMaterial(knowledge_id=key, explanation="Relis la leçon.", sorting=sorting)
    return KnowledgeUnit(item=item, material=material, subject=subject, grade=grade)


# Tableaux recopiés d'un Bescherelle, pas calculés.
TABLES = {
    ("manger", Tense.PRESENT): ("mange", "manges", "mange", "mangeons", "mangez", "mangent"),
    ("commencer", Tense.IMPARFAIT): (
        "commençais",
        "commençais",
        "commençait",
        "commencions",
        "commenciez",
        "commençaient",
    ),
    ("finir", Tense.PRESENT): ("finis", "finis", "finit", "finissons", "finissez", "finissent"),
    ("finir", Tense.FUTUR): ("finirai", "finiras", "finira", "finirons", "finirez", "finiront"),
    ("chanter", Tense.PASSE_COMPOSE): (
        "ai chanté",
        "as chanté",
        "a chanté",
        "avons chanté",
        "avez chanté",
        "ont chanté",
    ),
    ("être", Tense.IMPARFAIT): ("étais", "étais", "était", "étions", "étiez", "étaient"),
    ("aller", Tense.FUTUR): ("irai", "iras", "ira", "irons", "irez", "iront"),
    ("faire", Tense.PRESENT): ("fais", "fais", "fait", "faisons", "faites", "font"),
    ("nager", Tense.IMPARFAIT): ("nageais", "nageais", "nageait", "nagions", "nagiez", "nageaient"),
    # Les verbes du 3e groupe du programme du CE1-CE2.
    ("dire", Tense.PRESENT): ("dis", "dis", "dit", "disons", "dites", "disent"),
    ("prendre", Tense.PRESENT): ("prends", "prends", "prend", "prenons", "prenez", "prennent"),
    ("venir", Tense.PRESENT): ("viens", "viens", "vient", "venons", "venez", "viennent"),
    ("pouvoir", Tense.FUTUR): ("pourrai", "pourras", "pourra", "pourrons", "pourrez", "pourront"),
    ("vouloir", Tense.PRESENT): ("veux", "veux", "veut", "voulons", "voulez", "veulent"),
    ("voir", Tense.IMPARFAIT): ("voyais", "voyais", "voyait", "voyions", "voyiez", "voyaient"),
    ("voir", Tense.PASSE_COMPOSE): ("ai vu", "as vu", "a vu", "avons vu", "avez vu", "ont vu"),
}


@pytest.mark.parametrize(("verb", "tense"), list(TABLES))
def test_the_code_conjugates_right(verb: str, tense: Tense) -> None:
    assert conjugate(verb, tense) == TABLES[verb, tense]


def test_unknown_verbs_and_tenses_are_refused() -> None:
    assert conjugate("appeler", Tense.PRESENT) is None  # radical qui change : pas proposé
    assert conjugate("aller", Tense.PASSE_COMPOSE) is None  # auxiliaire être : accord incertain
    assert conjugate("venir", Tense.PASSE_COMPOSE) is None


def test_the_verb_of_the_lesson_never_another(registry: ActivityRegistry) -> None:
    """Vraie leçon de CE1 « Le verbe dire au présent » : on conjugue dire ; une leçon sur un verbe
    que le code ne connaît pas n'a pas de jeu, plutôt que « chanter » à sa place."""
    game = registry.get(C.CONJUGATION)
    dire = unit("Le verbe dire au présent", grade=Grade.CE1)
    assert {game.build([dire], 2, random.Random(seed)).payload["word"] for seed in range(10)} == {"dire"}
    assert not game.accepts(unit("Le verbe partir au présent", grade=Grade.CE1))
    assert game.accepts(unit("Les verbes du 1er groupe au présent"))


def test_the_tense_comes_from_the_notion() -> None:
    assert tense_of("Le futur des verbes du 1er groupe") is Tense.FUTUR
    assert tense_of("L'imparfait de être et avoir") is Tense.IMPARFAIT
    assert tense_of("Le passé composé avec avoir") is Tense.PASSE_COMPOSE
    assert tense_of("Conjuguer au présent") is Tense.PRESENT


def test_conjugation_game(registry: ActivityRegistry) -> None:
    game = registry.get(C.CONJUGATION)
    notion = unit("Le futur de être et avoir")
    assert game.accepts(notion)
    assert not game.accepts(unit("Le futur de être et avoir", subject=Subject.MATH))
    assert not game.accepts(unit("Les volcans"))
    for seed in range(20):
        easy = game.build([notion], 1, random.Random(seed))
        verb = easy.payload["word"]
        assert verb in ("être", "avoir") and easy.payload["prompt"] == f"Conjugue « {verb} » au futur."
        forms = conjugate(verb, Tense.FUTUR)
        assert forms is not None
        assert [r["text"] for r in easy.payload["items"]] == [
            "je" if verb == "être" else "j'",
            "tu",
            "il",
            "nous",
        ]
        assert easy.solution["expected"] == {f"p{p}": forms[p] for p in range(4)}
        hard = game.build([notion], 3, random.Random(seed))
        assert len(hard.payload["items"]) == 6 and len(hard.payload["choices"]) == 8  # 2 intrus
        assert game.grade(hard, respond(hard, lambda _: True)).score == 1
        half = game.grade(hard, respond(hard, lambda _: False))
        assert 0 < half.score < 1 and sum(d["correct"] for d in half.details) == 4
    with pytest.raises(InvalidResponse):
        game.grade(easy, {"answers": [["p9", "c1"]]})


def test_every_homophone_sentence_is_well_formed() -> None:
    for pair, blanks in HOMOPHONES.items():
        assert len(blanks) >= 6
        assert {b.answer for b in blanks} == set(pair)  # les deux mots servent
        for blank in blanks:
            assert blank.sentence.count("___") == 1 and blank.answer in pair
            assert not blank.sentence.startswith("___")  # pas de majuscule à deviner


def test_homophone_pairs_named_by_the_notion() -> None:
    assert homophone_pairs("Les homophones a / à") == [("a", "à")]
    assert homophone_pairs("Choisir entre et ou est") == [("et", "est")]
    assert homophone_pairs("Le chat a mangé à midi") == []  # une phrase, pas une leçon d'homophones
    assert len(homophone_pairs("Les homophones grammaticaux")) == len(HOMOPHONES)


def test_homophone_game(registry: ActivityRegistry) -> None:
    game = registry.get(C.HOMOPHONE)
    activity = game.build([unit("Les homophones a / à et et / est")], 3, random.Random(2))
    assert len(activity.payload["items"]) == 6
    for item in activity.payload["items"]:
        assert item["choices"] in (["a", "à"], ["et", "est"])
    assert game.grade(activity, respond(activity, lambda _: True)).score == 1
    wrong = game.grade(activity, respond(activity, lambda _: False))
    assert wrong.score == 0 and all(not d["correct"] for d in wrong.details)
    # CE1 : seulement les premières paires, même si la leçon parle d'homophones en général.
    early = game.build([unit("Les homophones", grade=Grade.CE1)], 2, random.Random(1))
    assert {tuple(i["choices"]) for i in early.payload["items"]} <= {
        ("a", "à"),
        ("et", "est"),
        ("son", "sont"),
        ("on", "ont"),
    }


SCIENCE = Sorting(
    prompt="Range les animaux.",
    categories=[
        SortingBox(name="vivipares", members=["chien", "vache", "baleine", "chat"]),
        SortingBox(name="ovipares", members=["poule", "tortue", "grenouille", "serpent"]),
    ],
)


@pytest.mark.parametrize("seed", range(15))
def test_word_hunt_from_the_lesson_and_from_the_lexicon(registry: ActivityRegistry, seed: int) -> None:
    game = registry.get(C.WORD_HUNT)
    animals = unit("Les animaux", subject=Subject.SCIENCE, sorting=SCIENCE)
    activity = game.build([animals], 2, random.Random(seed))
    words = {w["id"]: w["text"] for w in activity.payload["words"]}
    category = activity.payload["prompt"].split("« ")[1].split(" »")[0]
    members = next(b.members for b in SCIENCE.categories if b.name == category)
    assert {words[i] for i in activity.solution["expected"]} == {w for w in words.values() if w in members}
    assert len(activity.solution["expected"]) >= 2 and len(words) - len(activity.solution["expected"]) >= 3

    nature = game.build([unit("La nature des mots : nom, verbe, adjectif")], 3, random.Random(seed))
    words = {w["id"]: w["text"] for w in nature.payload["words"]}
    wanted = nature.payload["prompt"].removeprefix("Touche tous les ").rstrip(".")
    listed = LEXICON[next(iter(LEXICON))][wanted]
    assert {words[i] for i in nature.solution["expected"]} == {w for w in words.values() if w in listed}
    assert game.grade(nature, {"selected": nature.solution["expected"]}).score == 1
    assert game.grade(nature, {"selected": nature.solution["expected"][1:]}).score < 1


def test_word_hunt_needs_categories(registry: ActivityRegistry) -> None:
    assert not registry.get(C.WORD_HUNT).accepts(unit("Les volcans", subject=Subject.SCIENCE))
    assert registry.get(C.WORD_HUNT).accepts(unit("Le pluriel des noms"))


def test_history_dates_go_on_a_timeline(registry: ActivityRegistry) -> None:
    game = registry.get(C.NUMBER_LINE)
    history = load_lesson("history_cm1_revolution.json")
    date = history.units["k1"].model_copy(update={"subject": Subject.HISTORY})
    assert game.accepts(date) and not game.accepts(history.units["k6"])  # un terme : pas de date
    for difficulty in (1, 2, 3):
        activity = game.build([date], difficulty, random.Random(difficulty))
        labels = {lab["index"]: int(lab["text"]) for lab in activity.payload["labels"]}
        (i, a), (j, b) = sorted(labels.items())[:2]
        step = (b - a) // (j - i)
        nearest = min(range(11), key=lambda k: abs(a + step * (k - i) - 1789))
        assert nearest in activity.solution["accepted"]
        assert game.grade(activity, {"index": nearest}).score == 1
        assert game.grade(activity, {"index": (nearest + 3) % 10}).score == 0
    assert "Début de la Révolution française" in game.build([date], 3, random.Random(1)).payload["prompt"]


@pytest.mark.parametrize("code", NEW_GAMES)
def test_parent_view_and_simulated_pupil(registry: ActivityRegistry, code: ActivityCode) -> None:
    label = {
        C.WORD_HUNT: "Le masculin et le féminin",
        C.CONJUGATION: "Le présent des verbes du 1er groupe",
        C.HOMOPHONE: "Les homophones son / sont",
    }[code]
    game = registry.get(code)
    for difficulty in sorted(game.difficulties):
        activity = game.build([unit(label)], difficulty, random.Random(difficulty))
        assert game.grade(activity, respond(activity, lambda _: True)).score == 1
        wrong = respond(activity, lambda _: False)
        assert game.grade(activity, wrong).score < 1
        mistake = describe(registry, activity, wrong)
        assert mistake is not None and mistake.given and mistake.expected and "{" not in mistake.given
