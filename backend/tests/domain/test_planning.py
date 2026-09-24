"""Étape 16 : plan de révision avant un contrôle, et séance à la durée choisie par le parent."""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.domain.activities.registry import ActivityRegistry
from app.domain.composer import Block, SessionComposer
from app.domain.mastery import Mastery
from app.domain.planning import Focus, PlanDay, core_size, revision_plan, today_step
from tests.domain.conftest import ReferenceLesson

TODAY = date(2026, 9, 21)  # un lundi
D, T, M, E, X = Focus.DIAGNOSTIC, Focus.TARGETED, Focus.MEMORIZE, Focus.ERRORS, Focus.MOCK_TEST


def days(*offsets: int) -> list[date]:
    return [TODAY + timedelta(days=o) for o in offsets]


def steps(plan: list[PlanDay]) -> list[tuple[int, Focus]]:
    return [((p.day - TODAY).days, p.focus) for p in plan]


@pytest.mark.parametrize(
    ("days_left", "expected"),
    [
        (7, [(0, D), (1, T), (2, M), (3, E), (6, X)]),  # le mini-contrôle, la veille
        (5, [(0, D), (1, T), (2, M), (3, E), (4, X)]),
        (3, [(0, D), (1, T), (2, X)]),
        (2, [(0, D), (1, X)]),
        (1, [(0, X)]),  # contrôle demain : une séance complète
        (0, []),  # c'est aujourd'hui
    ],
)
def test_plan_fits_the_days_left(days_left: int, expected: list[tuple[int, Focus]]) -> None:
    assert steps(revision_plan(TODAY, TODAY + timedelta(days=days_left), [])) == expected


def test_a_missed_day_is_redistributed() -> None:
    exam = TODAY + timedelta(days=7)
    # Diagnostic fait lundi, rien mardi : mercredi, on reprend à « exercices ciblés ».
    wednesday = TODAY + timedelta(days=2)
    plan = revision_plan(wednesday, exam, days(0))
    assert [((p.day - wednesday).days, p.focus) for p in plan] == [(0, T), (1, M), (2, E), (4, X)]
    # Il ne reste que 2 jours : on garde le ciblé et le mini-contrôle.
    thursday = TODAY + timedelta(days=5)
    assert [p.focus for p in revision_plan(thursday, exam, days(0))] == [T, X]


def test_today_done_and_plan_end() -> None:
    exam = TODAY + timedelta(days=7)
    plan = revision_plan(TODAY, exam, days(0))
    step = today_step(plan, TODAY)
    assert step is not None and step.done and step.focus is D
    assert "leçon" in step.label
    # Toutes les étapes faites : plus de plan, la mission du jour reprend son cours.
    assert revision_plan(TODAY + timedelta(days=5), exam, days(0, 1, 2, 3, 4)) == []
    # Un jour libre entre la dernière étape et le mini-contrôle : pas d'étape ce jour-là.
    assert (
        today_step(revision_plan(TODAY, TODAY + timedelta(days=9), days(-1)), TODAY + timedelta(days=5))
        is None
    )


@pytest.mark.parametrize(("minutes", "size"), [(None, 3), (5, 0), (10, 3), (15, 6), (20, 9), (30, 12)])
def test_core_size_follows_the_daily_minutes(minutes: int | None, size: int) -> None:
    assert core_size(minutes) == size


NOW = datetime(2026, 9, 21, 17, tzinfo=UTC)


def test_session_length_follows_the_daily_minutes(
    history: ReferenceLesson, registry: ActivityRegistry
) -> None:
    composer = SessionComposer(registry)
    units = list(history.units.values())
    blocks = {
        size: [i.block for i in composer.compose(units, {}, NOW, seed=1, core_size=size).items]
        for size in (0, 3, 9)
    }
    assert Block.CORE not in blocks[0] and Block.MATCH not in blocks[0]
    assert blocks[3].count(Block.CORE) == 3
    assert blocks[9].count(Block.CORE) == 9
    minutes = [composer.compose(units, {}, NOW, seed=1, core_size=s).estimated_minutes for s in (0, 3, 9)]
    assert minutes == sorted(minutes) and minutes[0] < minutes[2]


def test_mock_test_includes_what_is_known(history: ReferenceLesson, registry: ActivityRegistry) -> None:
    composer = SessionComposer(registry)
    units = list(history.units.values())
    known = {u.id: Mastery(97, 5, NOW + timedelta(days=9), NOW, levels=frozenset({1, 2, 3})) for u in units}
    mock = composer.compose(units, known, NOW, seed=2, include_known=True)
    assert Block.CORE in {i.block for i in mock.items}
