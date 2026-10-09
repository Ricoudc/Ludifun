"""Rappels du jour (§48) : un au plus par enfant, le plus utile, jamais si l'enfant a déjà révisé,
« pas encore révisé » seulement en fin de journée et pour un enfant qui a une habitude."""

from app.domain.reminders import AFTER_HOUR, ChildDay, ReminderKind, reminder


def day(**changes: object) -> ChildDay:
    base: dict[str, object] = {"name": "Emma", "revised_today": False, "hour": AFTER_HOUR}
    base.update(changes)
    return ChildDay(**base)  # type: ignore[arg-type]


def test_nothing_once_the_child_has_revised() -> None:
    assert reminder(day(revised_today=True, exam=("Fractions", 1), due_today=["Numérateur"])) is None


def test_the_most_useful_reminder_only() -> None:
    exam = reminder(day(exam=("Fractions", 1), due_today=["Numérateur"], daily_minutes=15))
    assert exam is not None and exam.kind is ReminderKind.EXAM
    assert exam.text.startswith("📅 Contrôle « Fractions » demain : une petite séance avec Emma")
    review = reminder(day(due_today=["Numérateur", "Dénominateur", "Fraction"], exam=("Fractions", 5)))
    assert review is not None and review.kind is ReminderKind.REVIEW
    assert review.text == (
        "🔁 3 notion(s) à revoir aujourd'hui pour Emma : « Numérateur » et « Dénominateur » et 1 autre(s). "
        "Quelques minutes suffisent."
    )


def test_no_session_only_late_and_with_a_habit() -> None:
    assert reminder(day(daily_minutes=15, hour=AFTER_HOUR - 1)) is None
    assert reminder(day(hour=20)) is None  # pas d'habitude : pas de rappel
    late = reminder(day(daily_minutes=15, hour=20))
    assert late is not None and late.kind is ReminderKind.NO_SESSION
    assert (
        late.text
        == "⏰ Emma n'a pas encore révisé aujourd'hui (objectif : 15 min). Une courte séance avant le dîner ?"
    )
    assert reminder(day(days_active_last_week=3, hour=20)) is not None
