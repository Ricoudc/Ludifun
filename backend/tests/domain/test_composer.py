from datetime import UTC, datetime, timedelta
from itertools import pairwise

import pytest

from app.domain.activities.base import ActivityCode
from app.domain.activities.registry import ActivityRegistry
from app.domain.composer import (
    EASY,
    INTERMEDIATE,
    Block,
    NothingToReview,
    SessionComposer,
    SessionKind,
    SessionPlan,
)
from app.domain.mastery import Mastery
from tests.domain.conftest import ReferenceLesson

NOW = datetime(2026, 9, 23, 17, 0, tzinfo=UTC)


@pytest.fixture
def composer(registry: ActivityRegistry) -> SessionComposer:
    return SessionComposer(registry)


ALL_LEVELS = frozenset({1, 2, 3})


def mastery(score: int, box: int, due_in_days: float, levels: frozenset[int] = ALL_LEVELS) -> Mastery:
    """Par défaut, tous les niveaux de compréhension sont validés : seul le score compte."""
    return Mastery(score, box, NOW + timedelta(days=due_in_days), NOW - timedelta(days=2), levels=levels)


def blocks(plan: SessionPlan) -> list[Block]:
    return [item.block for item in plan.items]


def notions(plan: SessionPlan, *wanted: Block) -> list[str]:
    return [k for item in plan.items if item.block in wanted for k in item.activity.knowledge_ids]


def assert_common_rules(plan: SessionPlan) -> None:
    types = [item.activity.type for item in plan.items]
    assert all(a != b for a, b in pairwise(types)), types  # jamais deux fois de suite
    assert [item.position for item in plan.items] == list(range(1, len(plan.items) + 1))


# --------------------------------------------------------------------------- #
# Première révision (§8.1)
# --------------------------------------------------------------------------- #


def test_first_session_structure(lesson: ReferenceLesson, composer: SessionComposer) -> None:
    plan = composer.compose(list(lesson.units.values()), {}, NOW, seed=11)
    assert plan.kind is SessionKind.FIRST
    assert not plan.express
    assert blocks(plan) == [Block.WARMUP] * 3 + [Block.CORE] * 3 + [Block.MATCH, Block.SPEED]
    assert_common_rules(plan)
    for item in plan.items:
        if item.block is Block.WARMUP:
            assert (item.activity.difficulty, item.activity.type in EASY) == (1, True)
        if item.block is Block.CORE:
            assert item.activity.difficulty == 2
            assert item.activity.type in INTERMEDIATE
    match = plan.items[6].activity
    assert 3 <= len(match.knowledge_ids) <= 5
    assert len(plan.items[7].activity.payload["statements"]) == 5
    assert 4 <= plan.estimated_minutes <= 10


def test_first_session_starts_with_the_most_important_notions(
    history: ReferenceLesson, composer: SessionComposer
) -> None:
    plan = composer.compose(list(history.units.values()), {}, NOW, seed=1)
    assert notions(plan, Block.WARMUP) == ["k1", "k4", "k5"]  # importance 5
    assert notions(plan, Block.CORE) == ["k2", "k3", "k6"]  # importance 4, puis 3
    # 7 notions d'importance ≥ 3 : la notion d'importance 2 (k8) n'est pas utilisée.
    assert "k8" not in {k for item in plan.items for k in item.activity.knowledge_ids}
    # L'association privilégie ce qui n'a pas encore été vu.
    assert "k7" in plan.items[6].activity.knowledge_ids


def test_short_lesson_reuses_important_notions_with_another_format(
    math: ReferenceLesson, composer: SessionComposer
) -> None:
    plan = composer.compose(list(math.units.values()), {}, NOW, seed=4)
    assert notions(plan, Block.WARMUP) == ["k1", "k2", "k3"]
    assert notions(plan, Block.CORE) == ["k4", "k5", "k1"]
    k1_types = [i.activity.type for i in plan.items if i.activity.knowledge_ids == ["k1"]]
    assert len(k1_types) == 2 and k1_types[0] != k1_types[1]


def test_same_seed_same_session(history: ReferenceLesson, composer: SessionComposer) -> None:
    units = list(history.units.values())
    assert composer.compose(units, {}, NOW, seed=99) == composer.compose(units, {}, NOW, seed=99)
    plans = {str(composer.compose(units, {}, NOW, seed=s).items) for s in range(5)}
    assert len(plans) > 1


def test_duration_estimate(history: ReferenceLesson, composer: SessionComposer) -> None:
    plan = composer.compose(list(history.units.values()), {}, NOW, seed=1)
    base = sum(composer.registry.get(i.activity.type).base_duration_s for i in plan.items)
    assert plan.estimated_duration_s == base + 13 * len(plan.items) + 18


# --------------------------------------------------------------------------- #
# Révisions suivantes (§8.3)
# --------------------------------------------------------------------------- #


def test_review_focuses_on_fragile_and_due_notions(
    history: ReferenceLesson, composer: SessionComposer
) -> None:
    masteries = {
        "k1": mastery(95, 4, due_in_days=5),  # connue, pas due : exclue
        "k2": mastery(84, 3, due_in_days=-1),  # due
        "k3": mastery(42, 1, due_in_days=-1),  # fragile et due : en premier
        "k4": mastery(96, 4, due_in_days=5),  # connue : exclue
        "k5": mastery(60, 2, due_in_days=1),
        "k6": mastery(100, 2, due_in_days=1),  # connue : exclue
        "k7": mastery(30, 1, due_in_days=0.5),
    }
    plan = composer.compose(list(history.units.values()), masteries, NOW, seed=3)
    assert plan.kind is SessionKind.REVIEW
    # Score estimé aujourd'hui (1.5.0, §130) : pratiquées il y a 2 jours, k5 (boîte 2) vaut ~48 et
    # passe, plus importante, devant k7.
    assert notions(plan, Block.WARMUP) == ["k3", "k5", "k7"]
    assert notions(plan, Block.CORE)[0] == "k2"
    worked = set(notions(plan, Block.WARMUP, Block.CORE))
    assert not worked & {"k1", "k4", "k6"}
    by_notion = {i.activity.knowledge_ids[0]: i.activity.difficulty for i in plan.items[:4]}
    assert by_notion["k3"] == 1  # score < 50
    assert by_notion["k5"] == 2  # 50 à 79
    assert by_notion["k2"] in (2, 3)  # ≥ 80
    assert_common_rules(plan)


def test_express_review_when_few_notions_remain(history: ReferenceLesson, composer: SessionComposer) -> None:
    masteries = {k: mastery(98, 4, due_in_days=4) for k in history.units}
    masteries["k3"] = mastery(55, 2, due_in_days=-1)
    plan = composer.compose(list(history.units.values()), masteries, NOW, seed=5)
    assert plan.express
    assert blocks(plan) == [Block.WARMUP, Block.SPEED]
    assert plan.items[0].activity.knowledge_ids == ["k3"]
    assert "k3" in plan.items[1].activity.knowledge_ids  # le défi est complété par d'autres notions
    assert plan.estimated_minutes <= 2


def test_nothing_to_review(history: ReferenceLesson, composer: SessionComposer) -> None:
    masteries = {k: mastery(97, 5, due_in_days=10) for k in history.units}
    with pytest.raises(NothingToReview):
        composer.compose(list(history.units.values()), masteries, NOW, seed=5)


# --------------------------------------------------------------------------- #
# « Revoir mes erreurs » (§8.4)
# --------------------------------------------------------------------------- #


def test_errors_session(history: ReferenceLesson, composer: SessionComposer) -> None:
    plan = composer.compose_errors(list(history.units.values()), ["k3", "k6"], seed=2)
    assert plan.kind is SessionKind.ERRORS
    assert [i.activity.knowledge_ids[0] for i in plan.items] == ["k3", "k6", "k3", "k6"]
    for notion in ("k3", "k6"):
        types = {i.activity.type for i in plan.items if i.activity.knowledge_ids == [notion]}
        assert len(types) == 2
    assert not {i.activity.type for i in plan.items} & {ActivityCode.MATCH, ActivityCode.SPEED_CHALLENGE}
    assert_common_rules(plan)
    with pytest.raises(NothingToReview):
        composer.compose_errors(list(history.units.values()), [], seed=2)


@pytest.mark.parametrize("seed", range(40))
def test_rules_hold_for_many_seeds(lesson: ReferenceLesson, composer: SessionComposer, seed: int) -> None:
    units = list(lesson.units.values())
    plan = composer.compose(units, {}, NOW, seed)
    assert_common_rules(plan)
    assert blocks(plan) == [Block.WARMUP] * 3 + [Block.CORE] * 3 + [Block.MATCH, Block.SPEED]
    for item in plan.items:  # les formats et difficultés préférés sont toujours trouvés
        if item.block is Block.WARMUP:
            assert item.activity.difficulty == 1 and item.activity.type in EASY
        if item.block is Block.CORE:
            assert item.activity.difficulty == 2 and item.activity.type in INTERMEDIATE
    first_two_blocks = notions(plan, Block.WARMUP, Block.CORE)
    if len(units) >= 6:
        assert len(set(first_two_blocks)) == 6  # aucune notion deux fois dans les blocs 1 et 2
    # Même notion deux fois : jamais dans le même format.
    pairs = [(i.activity.knowledge_ids[0], i.activity.type) for i in plan.items[:6]]
    assert len(set(pairs)) == 6


def test_a_notion_not_seen_for_long_comes_first(history: ReferenceLesson, composer: SessionComposer) -> None:
    """§130 : à score égal, la notion travaillée il y a longtemps est sans doute plus oubliée."""
    units = [history.units["k2"], history.units["k5"]]
    old = Mastery(70, 2, NOW + timedelta(days=1), NOW - timedelta(days=20), levels=ALL_LEVELS)
    recent = Mastery(70, 2, NOW + timedelta(days=1), NOW - timedelta(days=1), levels=ALL_LEVELS)
    for first, other in (("k2", "k5"), ("k5", "k2")):
        plan = composer.compose(units, {first: old, other: recent}, NOW, seed=1)
        assert notions(plan, Block.WARMUP)[0] == first
