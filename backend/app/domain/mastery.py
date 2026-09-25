"""Mémorisation et prochaine révision (cahier des charges §10).

Chaque notion a, pour chaque apprenant, un score de maîtrise de 0 à 100, une boîte de 1 à 5
(qui fixe la date du prochain rappel) et les niveaux de compréhension déjà validés
(`app.domain.understanding`).
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.rules import RULES

# Seuils réglés dans engine_rules.toml.
REVIEW_INTERVAL_DAYS = RULES.mastery.review_interval_days
MIN_BOX, MAX_BOX = 1, 5
MASTERED_RATE = RULES.mastery.mastered_rate  # taux de séance au-dessus duquel la notion est maîtrisée
FRAGILE_RATE = RULES.mastery.fragile_rate  # en dessous : non maîtrisée
KNOWN_SCORE = RULES.mastery.known_score  # au-delà (et révision non due), la notion n'est plus proposée
IMPORTANT = (
    RULES.mastery.important
)  # importance à partir de laquelle une notion compte pour la date de révision


@dataclass(frozen=True)
class Mastery:
    score: int  # 0 à 100
    box: int  # 1 à 5
    next_review_at: datetime
    last_practiced_at: datetime
    sessions_count: int = 1
    levels: frozenset[int] = frozenset()  # niveaux de compréhension validés (1 à 5)

    def is_due(self, now: datetime) -> bool:
        return self.next_review_at <= now


def _round(value: float) -> int:
    return math.floor(value + 0.5)


def update_mastery(
    previous: Mastery | None, session_rate: float, now: datetime, validated: Iterable[int] = ()
) -> Mastery:
    """Met à jour la maîtrise d'une notion après une séance (§10.1).

    Première séance : on part de la boîte 1, donc une notion réussie du premier coup
    passe en boîte 2 (rappel à J+2). `validated` : niveaux de compréhension réussis pendant
    la séance ; un niveau validé le reste.
    """
    rate = min(1.0, max(0.0, session_rate))
    if previous is None:
        score = _round(100 * rate)
        box, count = MIN_BOX, 1
    else:
        score = _round(0.6 * 100 * rate + 0.4 * previous.score)
        box, count = previous.box, previous.sessions_count + 1
    levels = frozenset(validated) | (previous.levels if previous else frozenset())

    if rate >= MASTERED_RATE:
        box = min(MAX_BOX, box + 1)
    elif rate < FRAGILE_RATE:
        box = MIN_BOX

    return Mastery(
        score=score,
        box=box,
        next_review_at=now + timedelta(days=REVIEW_INTERVAL_DAYS[box]),
        last_practiced_at=now,
        sessions_count=count,
        levels=levels,
    )


@dataclass(frozen=True)
class LessonReview:
    next_review_at: datetime | None
    mastered: bool


def is_known(mastery: Mastery | None, required: frozenset[int]) -> bool:
    """Très bien maîtrisée : score ≥ 90, dernière boîte et tous les niveaux exigés validés."""
    return (
        mastery is not None
        and mastery.score >= KNOWN_SCORE
        and mastery.box == MAX_BOX
        and required <= mastery.levels
    )


def lesson_review(masteries: Iterable[tuple[int, Mastery | None, frozenset[int]]]) -> LessonReview:
    """Prochaine révision d'une leçon (§10.2), à partir de (importance, maîtrise, niveaux exigés)
    de ses notions.

    Les notions jamais travaillées ne fixent pas de date : la prochaine séance les
    proposera en priorité (leur score vaut 0).
    """
    important = [(m, req) for imp, m, req in masteries if imp >= IMPORTANT]
    practised = [m for m, _ in important if m is not None]
    next_review = min((m.next_review_at for m in practised), default=None)
    mastered = bool(important) and all(is_known(m, req) for m, req in important)
    return LessonReview(next_review_at=next_review, mastered=mastered)
