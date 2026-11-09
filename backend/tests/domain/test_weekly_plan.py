"""« Que travailler avec mon enfant cette semaine ? » (§5.71) : trois actions concrètes, tirées
des faits, de la plus urgente à la plus générale ; chacune dit quoi, comment et pourquoi."""

from datetime import date

import pytest

from app.domain.errors import ErrorType
from app.domain.weekly_plan import ERROR_GESTURES, WeakNotion, WeekFacts, week_actions

TODAY = date(2026, 11, 9)  # un lundi
WEAK = WeakNotion("Le numérateur", "Le numérateur est le nombre du haut.", "Les fractions")


def test_the_most_urgent_first_and_three_at_most() -> None:
    facts = WeekFacts(
        child="Emma",
        today=TODAY,
        awaiting_lessons=["Les centaines", "Le verbe aller"],
        exams=[("Contrôle de fractions", date(2026, 11, 12))],
        weak=WEAK,
        recurring=(ErrorType.READING, "Le numérateur"),
        days_active=1,
        reviews_due=4,
        lessons=5,
    )
    actions = week_actions(facts)
    assert [a.kind for a in actions] == ["review", "exam", "explain"]
    review, exam, explain = actions
    assert review.title == "Relire et valider « Les centaines »" and "1 autre" in review.why
    assert exam.title == "Préparer le contrôle « Contrôle de fractions » (jeudi)"
    assert "Le numérateur est le nombre du haut." in explain.detail and "Emma" in explain.detail


def test_errors_routine_and_reviews_when_nothing_is_urgent() -> None:
    facts = WeekFacts(
        child="Léo",
        today=TODAY,
        recurring=(ErrorType.CALCULATION, "Les additions"),
        days_active=1,
        reviews_due=2,
        daily_minutes=15,
        lessons=3,
    )
    actions = week_actions(facts)
    assert [a.kind for a in actions] == ["error", "routine", "due"]
    assert actions[0].title == "Poser les calculs sur papier" and "Les additions" in actions[0].why
    assert actions[1].title == "Fixer un moment de 15 min, 4 jours cette semaine"
    assert actions[1].why == "1 jour(s) de révision sur les 7 derniers."


def test_a_regular_child_with_nothing_due_is_invited_to_add_a_lesson() -> None:
    actions = week_actions(WeekFacts(child="Emma", today=TODAY, days_active=5, lessons=2))
    assert [a.kind for a in actions] == ["lesson"]
    empty = week_actions(WeekFacts(child="Emma", today=TODAY))
    assert [a.kind for a in empty] == ["lesson"] and empty[0].why == "Aucune leçon pour l'instant."


@pytest.mark.parametrize(("day", "said"), [(TODAY, "aujourd'hui"), (date(2026, 11, 10), "demain")])
def test_exam_day_in_words(day: date, said: str) -> None:
    action = week_actions(WeekFacts(child="Emma", today=TODAY, exams=[("Dictée", day)], lessons=1))[0]
    assert action.title.endswith(f"({said})")


def test_every_error_has_a_gesture_without_he_or_she() -> None:
    assert set(ERROR_GESTURES) == set(ErrorType)
    for error in ErrorType:
        action = week_actions(
            WeekFacts(child="Sam", today=TODAY, recurring=(error, "x"), lessons=1, days_active=5)
        )[0]
        text = f" {action.title} {action.detail} ".lower()
        # Le prénom ne dit pas si l'enfant est une fille ou un garçon : aucune phrase genrée.
        for gendered in (" il ", " elle ", " s'il ", " qu'il ", " qu'elle "):
            assert gendered not in text, (error, text)
