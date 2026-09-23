from datetime import UTC, datetime, timedelta

import pytest

from app.domain.activities.base import ActivityCode
from app.domain.activities.registry import ActivityRegistry
from app.domain.mastery import Mastery, lesson_review, update_mastery
from app.domain.scoring import (
    Evidence,
    KnowledgeStatus,
    evidence_weight,
    score_on_10,
    session_rates,
    status,
    summarize_session,
)

NOW = datetime(2026, 9, 23, 17, 0, tzinfo=UTC)


def mastery(score: int, box: int, due_in_days: float = 1) -> Mastery:
    return Mastery(score, box, NOW + timedelta(days=due_in_days), NOW - timedelta(days=3))


# --------------------------------------------------------------------------- #
# Maîtrise (§10)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "rate, score, box, days",
    [(1.0, 100, 2, 2), (0.8, 80, 2, 2), (0.79, 79, 1, 1), (0.5, 50, 1, 1), (0.2, 20, 1, 1)],
)
def test_first_session(rate: float, score: int, box: int, days: int) -> None:
    m = update_mastery(None, rate, NOW)
    assert (m.score, m.box, m.sessions_count) == (score, box, 1)
    assert m.next_review_at == NOW + timedelta(days=days)
    assert m.last_practiced_at == NOW


@pytest.mark.parametrize(
    "previous_box, rate, box, days",
    [(3, 0.9, 4, 7), (4, 1.0, 5, 14), (5, 1.0, 5, 14), (3, 0.6, 3, 4), (4, 0.3, 1, 1)],
)
def test_boxes_and_intervals(previous_box: int, rate: float, box: int, days: int) -> None:
    m = update_mastery(mastery(60, previous_box), rate, NOW)
    assert m.box == box
    assert m.next_review_at == NOW + timedelta(days=days)


def test_score_blends_session_and_history() -> None:
    m = update_mastery(mastery(40, 1), 1.0, NOW)
    assert m.score == 76  # 0,6 × 100 + 0,4 × 40
    assert m.sessions_count == 2


def test_lesson_review_date_and_mastered_flag() -> None:
    soon, later = mastery(95, 5, due_in_days=2), mastery(95, 5, due_in_days=9)
    review = lesson_review([(5, later), (4, soon), (2, mastery(10, 1, due_in_days=0.5))])
    assert review.next_review_at == soon.next_review_at  # les notions d'importance ≤ 2 ne comptent pas
    assert review.mastered

    assert not lesson_review([(5, later), (4, mastery(95, 4))]).mastered  # pas encore en boîte 5
    assert not lesson_review([(5, later), (3, None)]).mastered  # une notion jamais travaillée
    assert lesson_review([(4, None)]).next_review_at is None


# --------------------------------------------------------------------------- #
# Notation (§9)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "code, difficulty, weight",
    [
        (ActivityCode.MCQ, 1, 0.6),
        (ActivityCode.MCQ, 3, 1.0),
        (ActivityCode.FILL_BLANK, 2, 0.8),
        (ActivityCode.TRUE_FALSE, 1, 0.3),
        (ActivityCode.SPEED_CHALLENGE, 1, 0.3),
        (ActivityCode.FLASHCARD, 2, 0.4),
        (ActivityCode.MATCH, 2, 0.8),
    ],
)
def test_evidence_weights(
    registry: ActivityRegistry, code: ActivityCode, difficulty: int, weight: float
) -> None:
    assert evidence_weight(code, difficulty, registry) == pytest.approx(weight)


def test_failed_then_replayed_notion_is_to_review() -> None:
    """Exemple du §9.3 : ratée en QCM, réussie en reprise → environ 0,5 → à revoir."""
    rates = session_rates(
        [
            Evidence("k1", 0.0, 0.6, ActivityCode.MCQ),
            Evidence("k1", 1.0, 0.8, ActivityCode.FILL_BLANK, replay=True),
            Evidence("k2", 1.0, 0.6, ActivityCode.MCQ),
        ]
    )
    assert rates == {"k1": pytest.approx(0.8 / 1.4), "k2": 1.0}
    assert status(rates["k1"]) is KnowledgeStatus.TO_REVIEW


@pytest.mark.parametrize(
    "rate, expected",
    [(1.0, "mastered"), (0.8, "mastered"), (0.79, "to_review"), (0.5, "to_review"), (0.49, "not_mastered")],
)
def test_status_thresholds(rate: float, expected: str) -> None:
    assert status(rate) == expected


@pytest.mark.parametrize(
    "scores, note",
    [
        ([], 0.0),
        ([1.0] * 8, 10.0),
        ([1, 1, 1, 1, 1, 1, 0, 0.5], 8.0),
        ([1, 1, 1, 1, 1, 0.5], 9.0),
        ([0.83], 8.5),
    ],
)
def test_score_on_10(scores: list[float], note: float) -> None:
    assert score_on_10(scores) == note


def test_summarize_session() -> None:
    evidences = [
        Evidence("k1", 1.0, 0.6, ActivityCode.MCQ),
        Evidence("k2", 0.0, 0.8, ActivityCode.FILL_BLANK),
        Evidence("k2", 1.0, 0.6, ActivityCode.MCQ, replay=True),
        Evidence("k3", 0.0, 0.6, ActivityCode.MCQ),
    ]
    before = {"k1": mastery(70, 2, due_in_days=-1)}
    outcome = summarize_session([1.0, 0.0, 0.0], evidences, before, {"k1": 5, "k2": 4, "k3": 3, "k4": 3}, NOW)
    assert outcome.score_on_10 == 3.5
    assert [(r.knowledge_id, r.status) for r in outcome.results] == [
        ("k3", "not_mastered"),
        ("k2", "not_mastered"),  # 0,6 / 1,4 ≈ 0,43
        ("k1", "mastered"),
    ]
    k1 = outcome.results[-1].mastery
    assert (k1.score, k1.box, k1.sessions_count) == (88, 3, 2)
    assert outcome.next_review_at == NOW + timedelta(days=1)
    assert not outcome.lesson_mastered  # k4 jamais travaillée
    assert outcome.count(KnowledgeStatus.NOT_MASTERED) == 2
    assert outcome.can_review_errors
    assert outcome.errors == ["k3", "k2"]
