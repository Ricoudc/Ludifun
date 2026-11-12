"""Étape 17 (domaine) : remédiation, proposition de pause, défis bonus."""

import random
from datetime import UTC, datetime

import pytest

from app.domain.activities.base import ActivityCode
from app.domain.activities.registry import ActivityRegistry
from app.domain.composer import EASY, Block, SessionComposer
from app.domain.engagement import Answer, HintKind, bonus_offered, engagement_hint
from app.domain.scoring import Evidence
from tests.domain.conftest import ReferenceLesson

NOW = datetime(2026, 9, 24, 17, tzinfo=UTC)


def wrong(ms: int | None = 9000) -> Answer:
    return Answer(0.0, ms)


def right(ms: int | None = 9000) -> Answer:
    return Answer(1.0, ms)


@pytest.mark.parametrize(
    ("answers", "since", "hint"),
    [
        ([right(), wrong(500), wrong(700), wrong(900)], None, HintKind.FAST_GUESSING),
        ([wrong(500), right(), wrong(700), right(), wrong(900)], None, HintKind.FAST_GUESSING),
        ([wrong(500), wrong(700), right(800)], None, None),  # une réponse rapide et juste : bien
        ([wrong(), wrong(), wrong(), wrong()], None, HintKind.STRUGGLING),
        ([wrong(), wrong(), right(), wrong()], None, None),
        ([wrong(500), wrong(700), wrong(900)], 3, None),  # pause déjà proposée il y a 3 réponses
        ([wrong(500), wrong(700), wrong(900)], 5, HintKind.FAST_GUESSING),
        ([wrong(None), wrong(None), wrong(None)], None, None),  # sans durée : pas de conclusion
    ],
)
def test_engagement_hint(answers: list[Answer], since: int | None, hint: HintKind | None) -> None:
    assert engagement_hint(answers, since) is hint


def test_bonus_offer() -> None:
    assert bonus_offered([1, 1, 0.8], answered_ms=60_000, estimated_s=300)
    assert not bonus_offered([1, 0.5, 0.6], answered_ms=60_000, estimated_s=300)  # pas assez réussie
    assert not bonus_offered([1, 1, 1], answered_ms=200_000, estimated_s=300)  # pas assez rapide
    assert not bonus_offered([], answered_ms=0, estimated_s=300)


def test_remediation_starts_easy_with_fresh_formats(
    history: ReferenceLesson, registry: ActivityRegistry
) -> None:
    composer = SessionComposer(registry)
    unit = history.unit("k3")
    failed = [registry.get(ActivityCode.MCQ).build([unit], 1, random.Random(1))]
    planned = composer.remediation(unit, failed, start_position=4, seed=7)
    assert [p.position for p in planned] == [4, 5]
    assert {p.block for p in planned} == {Block.REMEDIATION}
    first, second = (p.activity for p in planned)
    assert first.difficulty == 1 and first.type in EASY and first.type is not ActivityCode.MCQ
    assert second.type not in {ActivityCode.MCQ, first.type}
    assert all(p.activity.knowledge_ids == ["k3"] for p in planned)


def test_bonus_is_harder_and_new(history: ReferenceLesson, registry: ActivityRegistry) -> None:
    composer = SessionComposer(registry)
    units = list(history.units.values())
    plan = composer.compose(units, {}, NOW, seed=3)
    previous = [i.activity for i in plan.items]
    bonus = composer.bonus(units, {}, previous, start_position=len(previous) + 1, seed=3)
    assert 1 <= len(bonus) <= 3 and {b.block for b in bonus} == {Block.BONUS}
    assert all(b.activity.difficulty >= 2 for b in bonus)
    used = {(k, a.type) for a in previous for k in a.knowledge_ids}
    assert not any((k, b.activity.type) in used for b in bonus for k in b.activity.knowledge_ids)


def test_replay_reuses_a_format_when_all_were_failed(
    history: ReferenceLesson, registry: ActivityRegistry
) -> None:
    composer = SessionComposer(registry)
    unit = history.unit("k2")  # Louis XVI : QCM, vrai/faux, carte
    formats = {code for code, _ in registry.single_options(unit)}
    evidences = [Evidence("k2", 0.0, 1.0, code) for code in formats]
    replay = composer.replay([unit], evidences, [], start_position=1, seed=1)
    assert [p.activity.knowledge_ids for p in replay] == [["k2"]]
