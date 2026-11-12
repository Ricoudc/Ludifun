"""§5.76 : Ludi, un mot après chaque réponse, à l'âge de l'enfant, sans jamais de reproche."""

import pytest

from app.domain.coach import Age, Mood, age_of, coach_line
from app.domain.errors import ErrorType

FORBIDDEN = ("nul", "faux", "mauvais", "raté", "idiot", "les autres")


def test_ages() -> None:
    assert [age_of(g) for g in ("CP", "CE1", "CE2", "CM2", "6e", "3e", None)] == [
        Age.YOUNG,
        Age.YOUNG,
        Age.MIDDLE,
        Age.MIDDLE,
        Age.COLLEGE,
        Age.COLLEGE,
        Age.MIDDLE,
    ]


def test_the_error_says_what_to_look_at() -> None:
    line = coach_line("incorrect", grade="CM1", error=ErrorType.CALCULATION)
    assert line is not None and line.mood is Mood.THINKING
    assert line.message == "Tu y es presque ! Refais le calcul étape par étape."
    assert coach_line("partial", grade="CM1").message.startswith("Tu y es presque")  # type: ignore[union-attr]
    assert coach_line("skipped", grade="CM1") is None


def test_streaks_and_success_after_help() -> None:
    assert coach_line("correct", grade="CP", streak=3).message == "3 de suite, tu es un champion !"  # type: ignore[union-attr]
    assert coach_line("correct", grade="CP", streak=4).mood is Mood.HAPPY  # type: ignore[union-attr]
    helped = coach_line("correct", grade="5e", helped=True, streak=3)
    assert helped is not None and helped.mood is Mood.PROUD and "aide" in helped.message
    # Même réponse, même phrase : pas de hasard.
    assert coach_line("correct", grade="CE2", position=4) == coach_line("correct", grade="CE2", position=4)


@pytest.mark.parametrize("grade", ["CP", "CM1", "4e"])
@pytest.mark.parametrize("result", ["correct", "partial", "incorrect"])
def test_never_a_reproach(grade: str, result: str) -> None:
    for error in [None, *ErrorType]:
        for streak in (0, 3, 5, 10):
            line = coach_line(result, grade=grade, error=error, streak=streak, helped=streak == 5)
            assert line is not None
            words = f" {line.message.lower()} "
            assert not any(f" {w} " in words or f" {w}," in words for w in FORBIDDEN), line.message
            assert len(line.message) <= 120
