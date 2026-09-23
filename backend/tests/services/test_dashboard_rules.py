"""Règles de calcul du tableau de bord parent (§11) : semaines, temps, couleurs, tendance."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.dashboard import WeekStats, answer_seconds, color, trend_of, week_start

PARIS = ZoneInfo("Europe/Paris")


@pytest.mark.parametrize(
    ("moment", "monday"),
    [
        (datetime(2026, 9, 13, 21, 59, tzinfo=UTC), date(2026, 9, 7)),  # dimanche 23 h 59 à Paris
        (datetime(2026, 9, 13, 22, 0, tzinfo=UTC), date(2026, 9, 14)),  # lundi 0 h à Paris
        (datetime(2026, 10, 25, 22, 59, tzinfo=UTC), date(2026, 10, 19)),  # passage à l'heure d'hiver
        (datetime(2026, 10, 25, 23, 0, tzinfo=UTC), date(2026, 10, 26)),
    ],
)
def test_weeks_start_on_monday_in_family_timezone(moment: datetime, monday: date) -> None:
    assert week_start(moment, PARIS) == monday


def test_answer_time_is_capped() -> None:
    assert answer_seconds(12_000) == 20
    assert answer_seconds(None) == 8
    assert answer_seconds(3_600_000) == 300 + 8  # application laissée ouverte


@pytest.mark.parametrize(
    ("percent", "expected"),
    [(100, "green"), (80, "green"), (79, "orange"), (50, "orange"), (49, "red"), (0, "red")],
)
def test_colors_follow_report_thresholds(percent: int, expected: str) -> None:
    assert color(percent) == expected


def week(score: float | None) -> WeekStats:
    stats = WeekStats(date(2026, 9, 7), _scores=[] if score is None else [score])
    return stats.close()


def test_trend_compares_the_last_two_active_weeks() -> None:
    assert trend_of([week(None), week(6)]) is None
    assert trend_of([week(6), week(None), week(7)]) == "up"  # une semaine creuse est ignorée
    assert trend_of([week(8), week(7.5)]) == "down"
    assert trend_of([week(8), week(8.4)]) == "stable"
