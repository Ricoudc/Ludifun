"""Demande de la famille (étape 26) : une séance d'un peu moins de 10 minutes, et d'autres
questions quand l'enfant refait la leçon."""

import random
from datetime import UTC, datetime, timedelta

from app.domain.activities.registry import ActivityRegistry
from app.domain.composer import SessionComposer, fingerprint
from app.domain.mastery import Mastery
from app.domain.planning import core_size
from tests.domain.conftest import ReferenceLesson

NOW = datetime(2026, 10, 2, 8, tzinfo=UTC)


def test_ten_minutes_is_a_bit_less_than_ten_minutes(
    history: ReferenceLesson, registry: ActivityRegistry
) -> None:
    plan = SessionComposer(registry).compose(
        list(history.units.values()), {}, NOW, seed=1, core_size=core_size(10)
    )
    assert len(plan.items) >= 12
    assert 7 * 60 <= plan.estimated_duration_s <= 10 * 60


def test_a_second_session_asks_other_questions(history: ReferenceLesson, registry: ActivityRegistry) -> None:
    units = list(history.units.values())
    composer = SessionComposer(registry)
    first = composer.compose(units, {}, NOW, seed=1, core_size=core_size(10))
    asked = frozenset(fingerprint(i.activity) for i in first.items)
    due = {u.id: Mastery(60, 1, NOW - timedelta(days=1), NOW - timedelta(days=2)) for u in units}
    second = SessionComposer(registry).compose(units, due, NOW, seed=2, core_size=core_size(10), recent=asked)
    again = [fingerprint(i.activity) for i in second.items if fingerprint(i.activity) in asked]
    # La leçon de référence n'a pas de quoi tout renouveler, mais la plupart des questions changent.
    assert len(again) <= len(second.items) // 3, again
    # Sans historique, la même graine redonne exactement la même séance (rejouable).
    replay = SessionComposer(registry).compose(units, {}, NOW, seed=1, core_size=core_size(10))
    assert [fingerprint(i.activity) for i in replay.items] == [fingerprint(i.activity) for i in first.items]


def test_fingerprint_ignores_the_shuffle(history: ReferenceLesson, registry: ActivityRegistry) -> None:
    unit = next(u for u in history.units.values() if u.material.questions)
    mcq = registry.get("MCQ")
    a = mcq.build([unit], unit.material.questions[0].difficulty, random.Random(1))
    b = mcq.build([unit], unit.material.questions[0].difficulty, random.Random(2))
    same_question = a.payload["prompt"] == b.payload["prompt"]
    assert (fingerprint(a) == fingerprint(b)) is same_question
