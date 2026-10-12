"""Jeux de l'étape 26 : démêler, trouver la correspondance, roue aléatoire, ouvrir la boîte,
cartes aléatoires. Tout vient du matériel déjà validé de la leçon : rien n'est demandé à l'IA."""

import json
import random

import pytest

from app.domain.activities.base import ActivityCode, InvalidResponse
from app.domain.activities.registry import ActivityRegistry
from app.domain.activities.unjumble import sentence_of
from app.domain.composer import SessionComposer
from app.domain.instructions import instruction
from app.domain.knowledge import KnowledgeUnit
from app.domain.mistakes import describe
from app.domain.simulated_pupil import respond
from tests.domain.conftest import ReferenceLesson

MULTI = [
    (ActivityCode.FIND_MATCH, 2),
    (ActivityCode.WHEEL, 1),
    (ActivityCode.BOX, 1),
    (ActivityCode.RANDOM_CARDS, 2),
]


def group(
    registry: ActivityRegistry, code: ActivityCode, difficulty: int, units: list[KnowledgeUnit]
) -> list[KnowledgeUnit]:
    return SessionComposer(registry)._group(code, difficulty, units)


def test_unjumble_puts_the_lesson_sentence_back_in_order(
    history: ReferenceLesson, registry: ActivityRegistry
) -> None:
    unit = next(u for u in history.units.values() if sentence_of(u))
    game = registry.get(ActivityCode.UNJUMBLE)
    activity = game.build([unit], 2, random.Random(3))
    sentence = activity.solution["sentence"]
    words = activity.payload["words"]
    assert sorted(w["text"] for w in words) == sorted(sentence.split())
    assert " ".join(w["text"] for w in words) != sentence  # jamais déjà dans l'ordre
    assert "sentence" not in activity.payload  # la réponse reste sur le serveur
    assert activity.solution["display"] == sentence  # dernier niveau de l'aide « Je n'ai pas compris »

    good = game.grade(activity, respond(activity, lambda _: True))
    assert good.score == 1.0 and good.correct_answer == sentence
    half = list(activity.solution["words"])
    half[0], half[1] = half[1], half[0]
    partial = game.grade(activity, {"order": half})
    assert 0 < partial.score < 1
    assert game.grade(activity, {"order": []}).score == 0
    mistake = describe(registry, activity, respond(activity, lambda _: False))
    assert mistake is not None and mistake.expected == sentence


def test_unjumble_needs_a_sentence_of_four_to_ten_words(
    history: ReferenceLesson, registry: ActivityRegistry
) -> None:
    unit = next(iter(history.units.values()))
    long = unit.model_copy(
        update={
            "item": unit.item.model_copy(update={"statement": " ".join(["mot"] * 3 + ["long"] * 12)}),
            "material": unit.material.model_copy(update={"true_statements": ["Trop court."]}),
        }
    )
    assert sentence_of(long) is None
    assert not registry.get(ActivityCode.UNJUMBLE).accepts(long)


@pytest.mark.parametrize(("code", "difficulty"), MULTI)
def test_multi_notion_games_build_and_grade(
    history: ReferenceLesson, registry: ActivityRegistry, code: ActivityCode, difficulty: int
) -> None:
    units = group(registry, code, difficulty, list(history.units.values()))
    assert units, f"{code} : aucune combinaison dans la leçon d'histoire"
    game = registry.get(code)
    activity = game.build(units, difficulty, random.Random(5))
    json.dumps([activity.payload, activity.solution])  # stockés en JSONB

    good = game.grade(activity, respond(activity, lambda _: True))
    assert good.score == 1.0 and good.errors == {}
    # Chaque élément porte son texte : l'application l'affiche dans la correction.
    assert all(d["text"] and d["expected"] for d in good.details)
    bad = game.grade(activity, respond(activity, lambda _: False))
    assert bad.score == 0.0 and set(bad.errors) == set(bad.evidence)
    # Une notion sur deux connue : le résultat suit, notion par notion.
    known = set(list(good.evidence)[::2])
    mixed = game.grade(activity, respond(activity, lambda k: k in known))
    assert {k for k, v in mixed.evidence.items() if v == 1.0} == known

    mistake = describe(registry, activity, respond(activity, lambda _: False))
    assert mistake is not None and mistake.question and mistake.expected
    for grade in ("CP", "CM1", "3e"):
        assert instruction(code, grade)


def test_wheel_stops_on_three_different_segments_without_naming_the_notion(
    history: ReferenceLesson, registry: ActivityRegistry
) -> None:
    units = group(registry, ActivityCode.WHEEL, 1, list(history.units.values()))
    activity = registry.get(ActivityCode.WHEEL).build(units, 1, random.Random(1))
    payload = activity.payload
    assert len(payload["spins"]) == 3
    assert len({s["segment"] for s in payload["spins"]}) == 3
    segment_texts = {s["text"] for s in payload["segments"]}
    labels = {u.item.label for u in units}
    assert not segment_texts & labels  # une case ne donne jamais la réponse
    assert all("choices" in s and "prompt" in s for s in payload["spins"])
    assert "expected" not in json.dumps(payload)


def test_box_and_cards_hide_nothing_from_the_server(
    history: ReferenceLesson, registry: ActivityRegistry
) -> None:
    units = group(registry, ActivityCode.BOX, 1, list(history.units.values()))
    box = registry.get(ActivityCode.BOX).build(units, 1, random.Random(2))
    assert [b["number"] for b in box.payload["boxes"]] == list(range(1, len(units) + 1))
    with pytest.raises(InvalidResponse):
        registry.get(ActivityCode.BOX).grade(box, {"answers": [{"id": "q1", "choice_id": "a"}] * 2})

    cards_units = group(registry, ActivityCode.RANDOM_CARDS, 2, list(history.units.values()))
    cards = registry.get(ActivityCode.RANDOM_CARDS).build(cards_units, 2, random.Random(2))
    # Les deux faces sont dans la charge utile : l'enfant doit pouvoir retourner la carte.
    assert all(c["front"] and c["back"] for c in cards.payload["cards"])
    unanswered = registry.get(ActivityCode.RANDOM_CARDS).grade(cards, {"cards": []})
    assert unanswered.score == 0


def test_find_match_shows_one_clue_per_target(history: ReferenceLesson, registry: ActivityRegistry) -> None:
    units = group(registry, ActivityCode.FIND_MATCH, 2, list(history.units.values()))
    activity = registry.get(ActivityCode.FIND_MATCH).build(units, 2, random.Random(4))
    assert len(activity.payload["clues"]) == len(activity.payload["targets"]) == len(units)
    with pytest.raises(InvalidResponse):
        registry.get(ActivityCode.FIND_MATCH).grade(activity, {"answers": [["c1", "inconnu"]]})


def test_new_games_appear_in_review_sessions(history: ReferenceLesson, registry: ActivityRegistry) -> None:
    from datetime import UTC, datetime, timedelta

    from app.domain.mastery import Mastery

    now = datetime(2026, 10, 2, 8, tzinfo=UTC)
    units = list(history.units.values())
    composer = SessionComposer(registry)
    due = {u.id: Mastery(60, 1, now - timedelta(days=1), now - timedelta(days=2)) for u in units}
    seen = {i.activity.type for seed in range(40) for i in composer.compose(units, due, now, seed=seed).items}
    assert {ActivityCode.UNJUMBLE, ActivityCode.FIND_MATCH, ActivityCode.WHEEL, ActivityCode.BOX} <= seen


@pytest.mark.parametrize(
    ("sentence", "answers"),
    [
        # Cas réel (téléphone, octobre 2026) : « 8 + 7 = 15 » était refusé.
        ("7 + 8 = 15", {"8 + 7 = 15": True, "15 = 7 + 8": True, "7 = 8 + 15": False, "8 = 7 + 15": False}),
        ("15 - 8 = 7", {"15 - 7 = 8": True, "7 = 15 - 8": True, "8 - 15 = 7": False}),
        ("3 × 4 = 12", {"4 × 3 = 12": True, "12 = 4 × 3": True, "3 = 4 × 12": False}),
        (
            "La somme de 7 et 8 est 15",
            {"La somme de 8 et 7 est 15": True, "La somme de 15 et 8 est 7": False},
        ),
    ],
)
def test_unjumble_accepts_every_true_order_of_a_calculation(
    history: ReferenceLesson, registry: ActivityRegistry, sentence: str, answers: dict[str, bool]
) -> None:
    """Un calcul s'écrit dans plusieurs ordres justes (l'addition et la multiplication sont
    commutatives) ; un ordre faux, même avec les mêmes nombres, reste faux."""
    unit = next(iter(history.units.values()))
    unit = unit.model_copy(
        update={"material": unit.material.model_copy(update={"true_statements": [sentence]})}
    )
    game = registry.get(ActivityCode.UNJUMBLE)
    activity = game.build([unit], 2, random.Random(1))
    assert activity.solution["sentence"] == sentence
    ids = {text: id_ for id_, text in activity.solution["words"].items()}
    for answer, right in answers.items():
        grade = game.grade(activity, {"order": [ids[word] for word in answer.split()]})
        assert (grade.score == 1.0) is right, answer
    # Le mélange proposé n'est jamais déjà une écriture juste.
    shuffled = [w["text"] for w in activity.payload["words"]]
    assert game.grade(activity, {"order": [ids[w] for w in shuffled]}).score < 1


@pytest.mark.parametrize(
    ("grade", "most"),
    [("CP", 4), ("CE1", 5), ("CE2", 6), ("CM1", 7), ("CM2", 8), ("6e", 8), (None, 8)],
)
def test_unjumble_is_simpler_for_young_children(
    registry: ActivityRegistry, grade: str | None, most: int
) -> None:
    """§5.63 : au CP et au CE1, peu d'étiquettes, et les petits mots restent avec le mot qui
    les suit (« de la voisine ») ; la phrase reformée est toujours celle de la leçon."""
    from app.domain.activities.unjumble import pieces
    from app.domain.knowledge import Grade

    level = Grade(grade) if grade else None
    for sentence in (
        "Les mammifères sont des animaux qui allaitent leurs petits.",
        "Le chat de la voisine mange une souris grise.",
        "Il a mangé l'orange de sa sœur ?",
    ):
        labels = pieces(sentence, level)
        assert len(labels) <= most and " ".join(labels) == sentence
        if level in (Grade.CP, Grade.CE1, Grade.CE2):
            assert not {"le", "la", "les", "de", "une", "des", "il"} & {label.lower() for label in labels}
    assert pieces("Le chat de la voisine mange une souris grise.", Grade.CE1) == [
        "Le chat",
        "de la voisine",
        "mange",
        "une souris",
        "grise.",
    ]
    # Un calcul et une phrase à deux nombres : un mot par étiquette (8 + 7 ou 7 + 8).
    assert pieces("7 + 8 = 15", Grade.CP) == ["7", "+", "8", "=", "15"]
    assert pieces("La somme de 8 et 7 est 15.", Grade.CE1)[3:6] == ["8", "et", "7"]


def test_unjumble_with_labels_builds_and_grades(registry: ActivityRegistry) -> None:
    from app.domain.knowledge import Grade, KnowledgeItem, KnowledgeMaterial, KnowledgeType, KnowledgeUnit

    long = "Les mammifères sont des animaux qui allaitent leurs petits et ont des poils."
    short = "Le chat de la voisine mange une souris grise."
    item = KnowledgeItem(
        id="k1",
        type=KnowledgeType.FACT,
        label="Les mammifères",
        statement=long,
        importance=4,
        source_excerpt="x",
    )
    material = KnowledgeMaterial(knowledge_id="k1", explanation="Relis.", true_statements=[short])
    game = registry.get(ActivityCode.UNJUMBLE)
    for grade, count in ((Grade.CE1, 5), (Grade.CM2, 8)):
        unit = KnowledgeUnit(item=item, material=material, grade=grade)
        for seed in range(10):
            activity = game.build([unit], 2, random.Random(seed))
            words = activity.payload["words"]
            if grade is Grade.CE1:  # la phrase courte au CE1
                assert activity.solution["sentence"] == short and len(words) == count
            assert len(words) <= count
            assert [w["id"] for w in words] != list(activity.solution["words"])  # mélangée
            assert game.grade(activity, respond(activity, lambda _: True)).score == 1
            assert game.grade(activity, respond(activity, lambda _: False)).score < 1
            mistake = describe(registry, activity, respond(activity, lambda _: False))
            assert mistake is not None and "Démêler" in mistake.question
