"""Difficulté dynamique par notion (§36) : elle part du score, puis suit les dernières réponses ;
une erreur d'attention (lecture, consigne, hasard) ne fait pas baisser le niveau."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.activities.registry import ActivityRegistry
from app.domain.composer import SessionComposer
from app.domain.decisions import describe
from app.domain.difficulty import STEP_DOWN_AFTER, STEP_UP_AFTER, RecentAnswer, notion_difficulty
from app.domain.mastery import Mastery
from tests.domain.conftest import load_lesson

NOW = datetime(2026, 10, 9, 17, 0, tzinfo=UTC)
ALL = frozenset({1, 2, 3, 4, 5})


@pytest.fixture
def composer(registry: ActivityRegistry) -> SessionComposer:
    return SessionComposer(registry)


def mastery(score: int) -> Mastery:
    return Mastery(score, 3, NOW - timedelta(days=1), NOW - timedelta(days=2), levels=ALL)


def right(difficulty: int, quick: bool = False, helped: bool = False) -> RecentAnswer:
    return RecentAnswer(difficulty, 1.0, helped=helped, quick=quick)


def wrong(difficulty: int, error: str | None = "knowledge") -> RecentAnswer:
    return RecentAnswer(difficulty, 0.0, error_type=error)


def test_without_history_the_score_decides() -> None:
    assert notion_difficulty(None, []).preferred == (1,)
    assert notion_difficulty(mastery(40), []).preferred == (1,)
    assert notion_difficulty(mastery(60), []).preferred == (2, 1)
    assert notion_difficulty(mastery(90), []).preferred == (3, 2)


def test_successes_at_the_top_level_make_it_harder() -> None:
    up = notion_difficulty(mastery(60), [right(2)] * STEP_UP_AFTER)
    assert up.preferred == (3, 2) and up.adjust == "up"
    assert up.facts == {"successes": STEP_UP_AFTER, "target": 3}
    # Rapides : une réussite de moins suffit.
    assert notion_difficulty(mastery(60), [right(2, quick=True)] * (STEP_UP_AFTER - 1)).adjust == "up"
    # Avec de l'aide, ou à un niveau plus facile : on ne monte pas.
    assert notion_difficulty(mastery(60), [right(2, helped=True)] * STEP_UP_AFTER).adjust is None
    assert notion_difficulty(mastery(60), [right(1)] * STEP_UP_AFTER).adjust is None
    # Une réussite après un échec ne compte qu'à partir de l'échec.
    history = [right(2), right(2), wrong(2), right(2)]
    assert notion_difficulty(mastery(60), history).adjust is None
    # Déjà au plus haut : rien au-dessus.
    assert notion_difficulty(mastery(90), [right(3)] * 5).preferred == (3, 2)


def test_failures_that_show_a_gap_make_it_easier() -> None:
    down = notion_difficulty(mastery(60), [wrong(2)] * STEP_DOWN_AFTER)
    assert down.preferred == (1,) and down.adjust == "down"
    # Lecture trop rapide, consigne mal comprise, hasard : l'attention, pas le niveau.
    for error in ("reading", "statement", "random"):
        assert notion_difficulty(mastery(60), [wrong(2), wrong(2, error)]).adjust is None
    assert notion_difficulty(mastery(40), [wrong(1)] * 3).preferred == (1,)  # déjà au plus facile


def test_the_composer_uses_the_history_and_says_why(composer: SessionComposer) -> None:
    fractions = load_lesson("math_cm2_fractions.json")  # une notion avec des activités de niveau 3
    units = [fractions.units["k4"]]
    masteries = {"k4": Mastery(60, 3, NOW - timedelta(days=1), NOW - timedelta(days=2), levels=ALL)}
    plan = composer.compose(units, masteries, NOW, seed=1, history={"k4": [right(2)] * STEP_UP_AFTER})
    scored = [i for i in plan.items if i.reason and i.reason["rule"] == "by_score"]
    item = next(i for i in scored if i.activity.difficulty == 3)
    assert item.reason is not None and item.reason["facts"]["adjust"] == "up"
    # Une activité restée au niveau 2 (pas de jeu de niveau 3) ne prétend pas avoir monté.
    assert all("adjust" not in i.reason["facts"] for i in scored if i.reason and i.activity.difficulty == 2)
    assert "Plus difficile : 3 réussites d'affilée sans aide." in (describe(item.reason) or "")
    plain = composer.compose(units, masteries, NOW, seed=1)
    assert all(i.activity.difficulty <= 2 for i in plain.items if i.reason and i.reason["rule"] == "by_score")
