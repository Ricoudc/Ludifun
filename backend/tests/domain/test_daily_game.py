"""§5.54 : jeu du jour — un jeu différent chaque jour, le même pour toutes les séances du jour,
glissé dans la séance avec sa raison, sans casser les règles de la séance."""

from datetime import timedelta
from itertools import pairwise

import pytest

from app.domain.activities.base import ActivityCode
from app.domain.activities.registry import ActivityRegistry
from app.domain.composer import DAILY_GAMES, Block, SessionComposer, SessionPlan
from app.domain.decisions import Rule, describe
from app.domain.knowledge import Grade
from tests.domain.conftest import ReferenceLesson, load_lesson
from tests.domain.test_composer import NOW
from tests.domain.test_math_games import unit as math_unit


def daily(plan: SessionPlan) -> list[tuple[int, ActivityCode]]:
    items = plan.items
    return [
        (i, item.activity.type)
        for i, item in enumerate(items)
        if item.reason.get("rule") == Rule.DAILY_GAME or item.reason["facts"].get("daily_game")
    ]


@pytest.mark.parametrize("seed", range(25))
def test_one_daily_game_per_session_and_the_rules_hold(
    lesson: ReferenceLesson, registry: ActivityRegistry, seed: int
) -> None:
    plan = SessionComposer(registry, daily_game=True).compose(list(lesson.units.values()), {}, NOW, seed)
    found = daily(plan)
    assert len(found) <= 1
    types = [item.activity.type for item in plan.items]
    assert all(a != b for a, b in pairwise(types)), types  # jamais deux fois de suite
    assert [item.position for item in plan.items] == list(range(1, len(plan.items) + 1))
    for index, code in found:
        item = plan.items[index]
        assert code in DAILY_GAMES and item.block in (Block.WARMUP, Block.CORE)
        sentence = describe(item.reason)
        assert sentence is not None and DAILY_GAMES[code] in sentence
    assert plan.estimated_minutes <= 10


def test_same_game_all_day_and_it_changes_the_next_day(registry: ActivityRegistry) -> None:
    """Une leçon de maths qui permet plusieurs jeux du jour : la rotation les parcourt tous."""
    notions = [
        math_unit("Lire l'heure", Grade.CE2, key="k1"),
        math_unit("La monnaie", Grade.CE2, key="k2"),
        math_unit("Mesurer des longueurs", Grade.CE2, key="k3"),
        math_unit("La symétrie", Grade.CE2, key="k4"),
    ]
    composer = SessionComposer(registry, daily_game=True)

    def game(day: int, seed: int) -> ActivityCode:
        plan = composer.compose(notions, {}, NOW + timedelta(days=day), seed)
        ((_, code),) = daily(plan)
        return code

    assert {game(0, seed) for seed in range(6)} == {game(0, 0)}  # même jeu toute la journée
    week = [game(day, 1) for day in range(8)]
    assert len(set(week)) >= 4 and all(a != b for a, b in pairwise(week))


def test_added_daily_game_has_its_own_reason(registry: ActivityRegistry) -> None:
    history = load_lesson("history_cm1_revolution.json")  # frise d'histoire : droite graduée
    composer = SessionComposer(registry, daily_game=True)
    reasons = []
    for day in range(10):
        plan = composer.compose(list(history.units.values()), {}, NOW + timedelta(days=day), 3)
        for index, _ in daily(plan):
            reasons.append(plan.items[index].reason)
    added = [r for r in reasons if r["rule"] == Rule.DAILY_GAME]
    assert reasons and all(r["facts"]["name"] in DAILY_GAMES.values() for r in reasons)
    for r in added:
        assert str(describe(r)).startswith(f"Jeu du jour ({r['facts']['name']})")


def test_no_daily_game_when_the_rule_is_off(lesson: ReferenceLesson, registry: ActivityRegistry) -> None:
    plan = SessionComposer(registry, daily_game=False).compose(list(lesson.units.values()), {}, NOW, 1)
    assert daily(plan) == []
