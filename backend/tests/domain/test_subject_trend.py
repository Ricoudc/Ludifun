"""§5.75 : la matière qui décroche (note moyenne en baisse sur 4 semaines), et l'action du parent."""

from datetime import date, timedelta

from app.domain.subject_trend import SessionScore, Slipping, slipping_subject
from app.domain.weekly_plan import WeekFacts, week_actions

WEEK = date(2026, 11, 9)  # lundi de la semaine en cours


def scores(subject: str, weeks_ago: int, *values: float) -> list[SessionScore]:
    return [SessionScore(subject, WEEK - timedelta(weeks=weeks_ago), v) for v in values]


def test_a_subject_slips_when_its_average_drops() -> None:
    data = [
        *scores("math", 3, 8, 8),
        *scores("math", 2, 7),
        *scores("math", 1, 6),
        *scores("math", 0, 5),
        *scores("french", 3, 9),
        *scores("french", 2, 8),
        *scores("french", 1, 8),
        *scores("french", 0, 8.5),
    ]
    found = slipping_subject(data, WEEK)
    assert found == Slipping("math", 7.7, 5.5) and found.name == "les maths"


def test_one_bad_session_or_too_few_sessions_is_not_a_trend() -> None:
    assert slipping_subject([*scores("math", 3, 8), *scores("math", 0, 3, 4)], WEEK) is None  # 1 avant
    assert slipping_subject([*scores("math", 2, 8, 8), *scores("math", 0, 7.5, 7)], WEEK) is None  # -0,75
    assert slipping_subject([*scores("math", 5, 9, 9), *scores("math", 0, 3, 3)], WEEK) is None  # trop ancien


def test_the_parent_is_told_which_subject_and_by_how_much() -> None:
    facts = WeekFacts(child="Sam", today=WEEK, lessons=2, days_active=5, slipping=Slipping("math", 7.5, 5))
    action = week_actions(facts)[0]
    assert action.kind == "subject" and action.title == "Reprendre les maths avec Sam"
    assert action.why == "Note moyenne en baisse : 7,5 → 5 / 10 sur les 4 dernières semaines."
    text = f" {action.title} {action.detail} ".lower()
    assert not any(g in text for g in (" il ", " elle ", " lui ", " d'elle "))
