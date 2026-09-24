"""Activités graphiques (étape 21) : remettre dans l'ordre, frise, ranger, memory."""

import random
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.activities.base import ActivityCode, InvalidResponse
from app.domain.activities.ordering import comparable, date_key
from app.domain.activities.registry import ActivityRegistry
from app.domain.composer import SessionComposer
from app.domain.knowledge import KnowledgeType, KnowledgeUnit
from app.domain.mastery import Mastery
from app.domain.simulated_pupil import respond
from app.domain.understanding import CognitiveLevel, cognitive_level, required_levels
from tests.domain.conftest import ReferenceLesson

NOW = datetime(2026, 9, 23, 17, 0, tzinfo=UTC)
STEPS = ["La bouche mâche", "L'œsophage transporte", "L'estomac brasse", "L'intestin absorbe"]


def process(history: ReferenceLesson) -> KnowledgeUnit:
    """Une notion « processus » (les étapes de la digestion), sur la base d'une notion existante."""
    base = history.unit("k1")
    item = base.item.model_copy(
        update={"type": KnowledgeType.PROCESS, "label": "La digestion", "attributes": {"steps": STEPS}}
    )
    return KnowledgeUnit(item=item, material=base.material)


@pytest.mark.parametrize(
    ("value", "key"),
    [
        ("1789", (1789, 0, 0)),
        ("14 juillet 1789", (1789, 7, 14)),
        ("1er août 1914", (1914, 8, 1)),
        ("mai 1968", (1968, 5, 0)),
        ("52 av. J.-C.", (-52, 0, 0)),
        ("il y a longtemps", None),
    ],
)
def test_date_key(value: str, key: tuple[int, int, int] | None) -> None:
    assert date_key(value) == key


def test_only_unambiguous_dates_are_compared() -> None:
    assert comparable((1789, 5, 5), (1789, 7, 14)) and comparable((1789, 0, 0), (1790, 7, 14))
    assert not comparable((1789, 0, 0), (1789, 5, 5))  # « 1789 » avant ou après le 5 mai 1789 ?
    assert not comparable((1789, 5, 0), (1789, 5, 5))
    assert comparable((1789, 5, 0), (1789, 7, 0))


def test_order_steps(history: ReferenceLesson, registry: ActivityRegistry) -> None:
    order = registry.get(ActivityCode.ORDER)
    unit = process(history)
    assert order.can_build([unit], 2) and cognitive_level(ActivityCode.ORDER, 2) is CognitiveLevel.RECALL
    activity = order.build([unit], 2, random.Random(3))
    shown = [i["text"] for i in activity.payload["items"]]
    assert sorted(shown) == sorted(STEPS) and shown != STEPS  # jamais déjà dans l'ordre
    assert activity.payload["prompt"] == "Remets dans l'ordre : La digestion"

    perfect = order.grade(activity, {"order": activity.solution["order"]})
    assert perfect.score == 1 and perfect.correct_answer == " → ".join(STEPS) and not perfect.errors
    s1, s2, s3, s4 = activity.solution["order"]
    half = order.grade(activity, {"order": [s1, s2, s4, s3]})
    assert half.score == 0.5 and half.errors == {unit.id: "method"}
    assert [d["correct"] for d in half.details] == [True, True, False, False]
    for bad in ({"order": [s1, s2, s3]}, {"order": [s1, s1, s2, s3]}, {"order": [s1, s2, s3, "s9"]}):
        with pytest.raises(InvalidResponse):
            order.grade(activity, bad)
    # Moins de 3 étapes : pas de jeu.
    two = unit.item.model_copy(update={"attributes": {"steps": STEPS[:2]}})
    assert not order.accepts(KnowledgeUnit(item=two, material=unit.material))


def test_timeline_on_the_revolution(history: ReferenceLesson, registry: ActivityRegistry) -> None:
    timeline = registry.get(ActivityCode.TIMELINE)
    events = [history.unit(k) for k in ("k3", "k4", "k5")]  # États généraux, Bastille, Déclaration
    assert timeline.can_build(events, 2)
    assert not timeline.can_build([history.unit("k1"), *events[:2]], 2)  # « 1789 » seule : ambigu
    activity = timeline.build(events, 2, random.Random(1))
    assert "5 mai 1789" in activity.solution["display"].split(" → ")[0]
    assert all(set(i) == {"id", "text"} for i in activity.payload["items"])  # sans les dates

    perfect = respond(activity, lambda _: True)
    assert timeline.grade(activity, perfect).score == 1
    wrong = timeline.grade(activity, respond(activity, lambda k: k != "k4"))
    assert wrong.score < 1 and "k4" in wrong.errors


def test_classify_the_states_of_water(science: ReferenceLesson, registry: ActivityRegistry) -> None:
    classify = registry.get(ActivityCode.CLASSIFY)
    unit = next(u for u in science.units.values() if classify.accepts(u))
    activity = classify.build([unit], 2, random.Random(2))
    categories = {c["id"] for c in activity.payload["categories"]}
    assert len(categories) >= 2 and len(activity.payload["items"]) >= 3
    assert classify.grade(activity, respond(activity, lambda _: True)).score == 1
    wrong = classify.grade(activity, respond(activity, lambda _: False))
    assert wrong.score == 0 and wrong.errors == {unit.id: "confusion"}
    first = activity.payload["items"][0]["id"]
    with pytest.raises(InvalidResponse):
        classify.grade(activity, {"assignments": [[first, "c1"]]})  # pas tout rangé
    assert required_levels(unit, registry) == {1, 2}


def test_memory_counts_moves_and_mistakes(history: ReferenceLesson, registry: ActivityRegistry) -> None:
    memory = registry.get(ActivityCode.MEMORY)
    units = [u for u in history.units.values() if memory.accepts(u)][:4]
    activity = memory.build(units, 1, random.Random(4))
    assert len(activity.payload["cards"]) == 8 and memory.evidence_factor == 0.5
    by_card = activity.solution["knowledge_by_card"]
    groups: dict[str, set[str]] = {}
    for card in activity.payload["cards"]:
        groups.setdefault(card["pair"], set()).add(by_card[card["id"]])
    assert len(groups) == 4 and all(len(k) == 1 for k in groups.values())  # une paire = une notion
    assert all(not card["pair"].startswith("k") for card in activity.payload["cards"])

    perfect = memory.grade(activity, respond(activity, lambda _: True))
    assert perfect.score == 1 and set(perfect.evidence.values()) == {1.0}
    missed = units[0].id
    struggling = memory.grade(activity, respond(activity, lambda k: k != missed))
    pair = units[0].material.pair
    assert pair is not None
    detail = next(d for d in struggling.details if d["id"] == missed)
    assert detail == {"id": missed, "correct": False, "mistakes": 2, "pair": f"{pair.left} ↔ {pair.right}"}
    assert struggling.evidence[missed] == 0.5 and struggling.score == 1  # 6 coups pour 4 paires
    first = activity.payload["cards"][0]["id"]
    with pytest.raises(InvalidResponse):
        memory.grade(activity, {"moves": [[first, first]]})
    with pytest.raises(InvalidResponse):
        memory.grade(activity, {"moves": [[first, activity.payload["cards"][1]["id"]]]})  # pas fini


def test_review_sessions_vary_the_puzzle(history: ReferenceLesson, registry: ActivityRegistry) -> None:
    """Première séance : l'association ; ensuite, association, frise ou memory selon la séance."""
    composer = SessionComposer(registry)
    units = list(history.units.values())
    first = composer.compose(units, {}, NOW, seed=1)
    assert [i.activity.type for i in first.items if i.block == "match"] == [ActivityCode.MATCH]

    due = {u.id: Mastery(40, 1, NOW - timedelta(days=1), NOW - timedelta(days=2)) for u in units}
    puzzles = {
        i.activity.type
        for seed in range(30)
        for i in composer.compose(units, due, NOW, seed=seed).items
        if i.block == "match"
    }
    assert puzzles == {ActivityCode.MATCH, ActivityCode.TIMELINE, ActivityCode.MEMORY}
