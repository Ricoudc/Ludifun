"""Rappels du jour pour le parent (cahier des charges §48), raisonnables et sans pression.

Au plus **un** rappel par enfant et par jour, le plus utile :

1. un contrôle aujourd'hui ou demain, pas encore révisé aujourd'hui ;
2. des notions à revoir aujourd'hui, pas encore de séance aujourd'hui ;
3. pas encore de séance aujourd'hui, pour un enfant qui a une habitude (un objectif quotidien,
   ou des révisions ces derniers jours) : seulement en fin de journée (`reminders.after_hour`).

Rien si l'enfant a déjà révisé aujourd'hui. Le ton propose, il ne reproche pas. Calculé par le
code à partir des données réelles ; le parent peut masquer les rappels du jour.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.domain.rules import RULES

AFTER_HOUR = RULES.reminders.after_hour
MAX_LABELS = 2


class ReminderKind(StrEnum):
    EXAM = "exam"
    REVIEW = "review"
    NO_SESSION = "no_session"


@dataclass(frozen=True)
class ChildDay:
    """La journée d'un enfant, telle que le serveur la connaît."""

    name: str
    revised_today: bool
    hour: int  # heure locale de la famille
    due_today: Sequence[str] = ()  # notions à revoir aujourd'hui (les plus importantes d'abord)
    daily_minutes: int | None = None
    days_active_last_week: int = 0
    exam: tuple[str, int] | None = None  # (titre, jours restants) du contrôle le plus proche


@dataclass(frozen=True)
class Reminder:
    kind: ReminderKind
    text: str


def _quote(labels: Sequence[str]) -> str:
    shown = [f"« {label} »" for label in labels[:MAX_LABELS]]
    more = len(labels) - MAX_LABELS
    text = " et ".join(shown) if len(shown) <= 2 else ", ".join(shown)
    return f"{text} et {more} autre(s)" if more > 0 else text


def reminder(day: ChildDay) -> Reminder | None:
    if day.revised_today:
        return None
    if day.exam is not None and day.exam[1] <= 1:
        title, days = day.exam
        when = "aujourd'hui" if days == 0 else "demain"
        return Reminder(
            ReminderKind.EXAM,
            f"📅 Contrôle « {title} » {when} : une petite séance avec {day.name}, "
            "pour l'aborder sereinement ?",
        )
    if day.due_today:
        count = len(day.due_today)
        return Reminder(
            ReminderKind.REVIEW,
            f"🔁 {count} notion(s) à revoir aujourd'hui pour {day.name} : {_quote(day.due_today)}. "
            "Quelques minutes suffisent.",
        )
    habit = day.daily_minutes is not None or day.days_active_last_week >= 2
    if habit and day.hour >= AFTER_HOUR:
        goal = f" (objectif : {day.daily_minutes} min)" if day.daily_minutes else ""
        return Reminder(
            ReminderKind.NO_SESSION,
            f"⏰ {day.name} n'a pas encore révisé aujourd'hui{goal}. Une courte séance avant le dîner ?",
        )
    return None
