"""Gamification (étape 20) : l'effort, le progrès et la régularité rapportent, jamais la note."""

from dataclasses import replace
from datetime import date, timedelta

import pytest

from app.db.models import BADGE_CODES
from app.domain.rewards import (
    BADGES,
    DAILY_XP_CAP,
    BadgeCode,
    Cheer,
    SessionFacts,
    cheer_text,
    earned_badges,
    encouragement,
    level_start,
    player_level,
    session_xp,
    streak,
)

BASE = SessionFacts(
    answered=12,
    level_ups=[],
    comebacks=[],
    newly_mastered=[],
    remediation=False,
    reviewed_errors=False,
    bonus=False,
    success_after_help=False,
    open_question_success=False,
    lesson_mastered=False,
    first_of_day=True,
    streak_days=1,
    sessions_completed=3,
    xp_today_before=0,
)


def xp(facts: SessionFacts) -> dict[str, int]:
    return {line.label: line.xp for line in session_xp(facts)}


def test_effort_is_rewarded_whatever_the_score() -> None:
    assert xp(BASE) == {"Séance terminée": 10, "Activités faites": 12}
    assert xp(replace(BASE, answered=40))["Activités faites"] == 20  # plafond
    everything = replace(
        BASE,
        level_ups=["k1", "k2"],
        comebacks=["k1", "k2", "k3", "k4"],
        remediation=True,
        success_after_help=True,
        reviewed_errors=True,
        bonus=True,
        streak_days=4,
    )
    assert xp(everything) == {
        "Séance terminée": 10,
        "Activités faites": 12,
        "Notions en progrès": 10,
        "Notions enfin réussies": 30,  # 3 au plus
        "Tu n'as rien lâché": 5,
        "Aide bien utilisée": 5,
        "Erreurs revues": 5,
        "Défis bonus": 5,
        "Régularité": 5,
    }
    # La régularité ne compte qu'à la première séance du jour.
    assert "Régularité" not in xp(replace(everything, first_of_day=False))


def test_daily_cap() -> None:
    assert xp(replace(BASE, xp_today_before=DAILY_XP_CAP - 15)) == {
        "Séance terminée": 10,
        "Activités faites": 5,
    }
    assert session_xp(replace(BASE, xp_today_before=DAILY_XP_CAP)) == []


@pytest.mark.parametrize(
    ("total", "level", "start", "next_"),
    [
        (0, 1, 0, 100),
        (99, 1, 0, 100),
        (100, 2, 100, 300),
        (299, 2, 100, 300),
        (300, 3, 300, 600),
        (1000, 5, 1000, 1500),
    ],
)
def test_player_level(total: int, level: int, start: int, next_: int) -> None:
    found = player_level(total)
    assert (found.level, found.start_xp, found.next_xp) == (level, start, next_)
    assert 0 <= found.progress(total) < 1
    assert level_start(1) == 0


def test_streak() -> None:
    today = date(2026, 9, 24)
    days = [today - timedelta(days=n) for n in (1, 2, 3, 5)]
    assert streak(days, today) == streak(days, today)  # déterministe
    # Pas encore révisé aujourd'hui : la série d'hier reste en cours.
    assert (streak(days, today).days, streak(days, today).done_today) == (3, False)
    assert streak([*days, today], today).days == 4
    # Une journée manquée : on recommence, sans reproche.
    assert streak([today - timedelta(days=2)], today).days == 0
    assert streak([], today).days == 0


def test_badges_are_earned_once() -> None:
    facts = replace(BASE, sessions_completed=1, comebacks=["k3"], streak_days=3)
    codes = [b.code for b in earned_badges(facts, [])]
    assert codes == [BadgeCode.FIRST_SESSION, BadgeCode.STREAK_3, BadgeCode.COMEBACK]
    assert earned_badges(facts, ["first_session", "streak_3", "comeback"]) == []
    # Aucun badge de note : les codes en base suivent le catalogue.
    assert set(BADGE_CODES) == {b.code.value for b in BADGES} == set(BadgeCode)


def test_encouragement_prefers_progress_over_score() -> None:
    assert encouragement(BASE).kind is Cheer.EFFORT
    assert encouragement(replace(BASE, remediation=True)).kind is Cheer.PERSEVERED
    assert encouragement(replace(BASE, level_ups=["k1"], remediation=True)).kind is Cheer.LEVEL_UP
    comeback = encouragement(replace(BASE, level_ups=["k1"], comebacks=["k3"]))
    assert (comeback.kind, comeback.knowledge_id) == (Cheer.COMEBACK, "k3")
    assert cheer_text(comeback, "États généraux", 1) == (
        "🏆 Tu as réussi une notion qui te posait problème : États généraux !"
    )
    assert encouragement(replace(BASE, streak_days=4)).kind is Cheer.STREAK
    for kind in Cheer:
        assert cheer_text(replace(comeback, kind=kind), "x", 2)
