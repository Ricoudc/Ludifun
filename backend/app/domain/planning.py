"""Objectifs du parent : temps de révision par jour et plan avant un contrôle (cahier des charges
complet §31, §33, §47 ; spécification technique §5.8, §5.9).

Le plan n'est pas enregistré : il est recalculé chaque jour à partir de la date du contrôle et
des jours où l'enfant a déjà révisé. Une journée manquée n'est donc jamais « en retard » : les
étapes restantes sont redistribuées sur les jours qui restent.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

DAILY_MINUTES = (5, 10, 15, 20, 30)
DEFAULT_MINUTES = 10
# Activités de l'approfondissement selon le temps du jour (l'échauffement en compte toujours 3,
# puis viennent le jeu de fin, le défi rapide et la reprise des erreurs). Réglé pour que la séance
# dure un peu moins que le temps choisi : 10 minutes → 13 activités, environ 9 minutes (étape 26 ;
# avant : 3, soit 8 activités et 5 minutes, jugé trop court par la famille).
CORE_SIZE = {5: 1, 10: 8, 15: 14, 20: 20, 30: 30}


class Focus(StrEnum):
    DIAGNOSTIC = "diagnostic"  # où en est l'enfant sur toute la leçon
    TARGETED = "targeted"  # les notions fragiles
    MEMORIZE = "memorize"  # retrouver sans aide ce qui est reconnu
    ERRORS = "errors"  # les notions encore ratées
    MOCK_TEST = "mock_test"  # mini-contrôle : toute la leçon, la veille


FOCUS_LABELS = {
    Focus.DIAGNOSTIC: "Où en es-tu ? Un tour de toute la leçon",
    Focus.TARGETED: "Exercices ciblés sur ce qui est fragile",
    Focus.MEMORIZE: "Mémoriser : retrouver les réponses seul",
    Focus.ERRORS: "Revoir tes erreurs",
    Focus.MOCK_TEST: "Mini-contrôle : comme le jour J",
}
TEMPLATE = (Focus.DIAGNOSTIC, Focus.TARGETED, Focus.MEMORIZE, Focus.ERRORS, Focus.MOCK_TEST)
# Quand il reste moins de jours que d'étapes, on retire d'abord celles-ci (jamais le mini-contrôle).
DROP_ORDER = (Focus.MEMORIZE, Focus.ERRORS, Focus.TARGETED, Focus.DIAGNOSTIC)


def core_size(minutes: int | None) -> int:
    """Activités d'approfondissement pour un temps quotidien (10 minutes par défaut)."""
    if minutes is None:
        return CORE_SIZE[DEFAULT_MINUTES]
    return CORE_SIZE[max(m for m in DAILY_MINUTES if m <= max(minutes, DAILY_MINUTES[0]))]


@dataclass(frozen=True)
class PlanDay:
    day: date
    focus: Focus
    done: bool = False

    @property
    def label(self) -> str:
        return FOCUS_LABELS[self.focus]


def revision_plan(today: date, exam_date: date, revised_on: Iterable[date]) -> list[PlanDay]:
    """Étapes à venir avant le contrôle, à partir d'aujourd'hui.

    `revised_on` : jours où l'enfant a terminé une séance sur les leçons du contrôle depuis sa
    création. Chaque jour de révision passé compte pour une étape ; les étapes restantes tiennent
    dans les jours qui restent (le mini-contrôle, toujours, la veille). Aujourd'hui fait partie
    du plan : si l'enfant a déjà révisé aujourd'hui, l'étape du jour est marquée faite.
    """
    days = sorted(set(revised_on))
    before = [d for d in days if d < today]
    remaining = list(TEMPLATE[min(len(before), len(TEMPLATE) - 1) :]) if len(before) < len(TEMPLATE) else []
    available = (exam_date - today).days  # d'aujourd'hui à la veille du contrôle
    if available <= 0 or not remaining:
        return []
    for focus in DROP_ORDER:
        if len(remaining) <= available:
            break
        if focus in remaining and len(remaining) > 1:
            remaining.remove(focus)
    remaining = remaining[-available:]

    plan = [PlanDay(today + timedelta(days=i), focus) for i, focus in enumerate(remaining[:-1])]
    plan.append(PlanDay(exam_date - timedelta(days=1), remaining[-1]))
    if today in days and plan[0].day == today:
        plan[0] = PlanDay(plan[0].day, plan[0].focus, done=True)
    return plan


def today_step(plan: list[PlanDay], today: date) -> PlanDay | None:
    return next((p for p in plan if p.day == today), None)
