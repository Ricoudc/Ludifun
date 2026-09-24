"""Adaptation en temps réel : remédiation, fatigue et défis bonus (cahier des charges complet
§32, §35 ; spécification technique §5.6 à §5.8).

Des règles simples et déterministes, sur les dernières réponses de la séance : pas de
diagnostic, seulement des propositions (« on fait une pause ? », « encore 3 défis ? »).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.domain.errors import RANDOM_BELOW_MS

REMEDIATION_AFTER_FAILURES = 2  # deux échecs sur la même notion : rappel puis activités faciles
MAX_REMEDIATIONS = 2  # par séance
FAILURE_BELOW = 0.5

WINDOW = 5  # réponses regardées
FAST_WRONG = 3  # réponses fausses et trop rapides dans la fenêtre : au hasard
STRUGGLING = 4  # échecs d'affilée
HINT_SPACING = 5  # au moins 5 réponses entre deux propositions de pause

BONUS_MIN_SCORE = 0.8
BONUS_MAX_TIME_SHARE = 0.6  # réponses données en moins de 60 % du temps prévu
BONUS_ACTIVITIES = 3


class HintKind(StrEnum):
    FAST_GUESSING = "fast_guessing"
    STRUGGLING = "struggling"


HINT_MESSAGES = {
    HintKind.FAST_GUESSING: (
        "Tu vas très vite ! On fait une petite pause, ou tu prends le temps de bien lire ?"
    ),
    HintKind.STRUGGLING: "Ce n'est pas facile aujourd'hui. Une petite pause te ferait du bien ?",
}


@dataclass(frozen=True)
class Answer:
    score: float  # 0 à 1
    duration_ms: int | None


def engagement_hint(answers: Sequence[Answer], answers_since_last_hint: int | None) -> HintKind | None:
    """Proposition de pause d'après les dernières réponses (la plus récente en dernier).

    Jamais deux propositions à moins de 5 réponses d'écart : on propose, on n'insiste pas.
    """
    if answers_since_last_hint is not None and answers_since_last_hint < HINT_SPACING:
        return None
    recent = list(answers[-WINDOW:])
    fast_wrong = sum(
        1
        for a in recent
        if a.score < FAILURE_BELOW and a.duration_ms is not None and a.duration_ms < RANDOM_BELOW_MS
    )
    if fast_wrong >= FAST_WRONG:
        return HintKind.FAST_GUESSING
    last = list(answers[-STRUGGLING:])
    if len(last) == STRUGGLING and all(a.score < FAILURE_BELOW for a in last):
        return HintKind.STRUGGLING
    return None


def bonus_offered(main_scores: Sequence[float], answered_ms: int, estimated_s: int) -> bool:
    """« Encore 3 défis ? » : séance bien réussie et nettement plus rapide que prévu."""
    if not main_scores:
        return False
    average = sum(main_scores) / len(main_scores)
    return average >= BONUS_MIN_SCORE and answered_ms <= BONUS_MAX_TIME_SHARE * estimated_s * 1000
