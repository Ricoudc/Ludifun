"""§5.73 : profil par notion pour le parent, et la décision qui en découle."""

from datetime import UTC, datetime, timedelta

from app.domain.mastery import Mastery
from app.domain.notion_profile import AdviceKind, notion_advice, time_sentence
from app.domain.state import Observation, notion_state
from app.domain.understanding import notion_level

NOW = datetime(2026, 11, 9, tzinfo=UTC)


def obs(i: int, score: float, help_level: int = 0, ms: int | None = 8000) -> Observation:
    return Observation(NOW - timedelta(hours=10 - i), 2, score, score, help_level, None, ms)


def mastery(score: int, levels: frozenset[int] = frozenset({1, 2}), due_in: int = 3) -> Mastery:
    return Mastery(
        score=score,
        box=3,
        next_review_at=NOW + timedelta(days=due_in),
        last_practiced_at=NOW - timedelta(hours=1),
        levels=levels,
    )


def test_profile_counts_time_and_last_answer() -> None:
    state = notion_state([obs(0, 1, ms=4000), obs(1, 0, ms=40_000), obs(2, 1, ms=9000), obs(3, 1, ms=None)])
    assert state.attempts == 4 and state.median_seconds == 9
    assert state.last_at == NOW - timedelta(hours=7)
    assert time_sentence(state) == "Temps de réponse habituel : 9 s."
    slow = notion_state([obs(0, 1, ms=45_000)])
    assert time_sentence(slow) is not None and "long" in str(time_sentence(slow))
    assert time_sentence(notion_state([])) is None


def test_never_practiced_has_no_advice() -> None:
    assert notion_advice(notion_level(None, [1, 2]), notion_state([]), None, NOW) is None


def test_fragile_goes_back_to_basics() -> None:
    m = mastery(30)
    advice = notion_advice(notion_level(m, [1, 2]), notion_state([obs(0, 0)]), m, NOW)
    assert advice is not None and advice.kind is AdviceKind.BASICS and advice.label == "Reprendre les bases"
    assert "30/100" in advice.why


def test_learning_or_helped_gets_more_exercises() -> None:
    m = mastery(65)
    advice = notion_advice(notion_level(m, [1, 2]), notion_state([obs(0, 1)]), m, NOW)
    assert advice is not None and advice.kind is AdviceKind.PRACTICE

    strong = mastery(90)
    missing = notion_advice(notion_level(strong, [1, 2, 3]), notion_state([obs(0, 1)]), strong, NOW)
    assert missing is not None and missing.kind is AdviceKind.PRACTICE and "« appliquer »" in missing.why

    helped = notion_state([obs(0, 1, help_level=2), obs(1, 1, help_level=3), obs(2, 1)])
    advice = notion_advice(notion_level(strong, [1, 2]), helped, strong, NOW)
    assert advice is not None and advice.kind is AdviceKind.PRACTICE and "33 % seul" in advice.why


def test_mastered_is_spaced_with_its_date() -> None:
    m = mastery(90)
    advice = notion_advice(notion_level(m, [1, 2]), notion_state([obs(0, 1)]), m, NOW)
    assert advice is not None and advice.kind is AdviceKind.SPACED and "le 12/11" in advice.why
    due = mastery(90, due_in=-1)
    advice = notion_advice(notion_level(due, [1, 2]), notion_state([obs(0, 1)]), due, NOW)
    assert advice is not None and "dès la prochaine séance" in advice.why
