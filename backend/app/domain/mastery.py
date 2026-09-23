"""Mémorisation et prochaine révision (cahier des charges §10).

Chaque notion a, pour chaque apprenant, un score de maîtrise de 0 à 100 (affiché)
et une boîte de 1 à 5 (qui fixe la date du prochain rappel).
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

REVIEW_INTERVAL_DAYS = {1: 1, 2: 2, 3: 4, 4: 7, 5: 14}
MIN_BOX, MAX_BOX = 1, 5
MASTERED_RATE = 0.8  # taux de séance au-dessus duquel la notion est maîtrisée
FRAGILE_RATE = 0.5  # en dessous : non maîtrisée
KNOWN_SCORE = 90  # au-delà (et révision non due), la notion n'est plus proposée
IMPORTANT = 3  # importance à partir de laquelle une notion compte pour la date de révision


@dataclass(frozen=True)
class Mastery:
    score: int  # 0 à 100
    box: int  # 1 à 5
    next_review_at: datetime
    last_practiced_at: datetime
    sessions_count: int = 1

    def is_due(self, now: datetime) -> bool:
        return self.next_review_at <= now


def _round(value: float) -> int:
    return math.floor(value + 0.5)


def update_mastery(previous: Mastery | None, session_rate: float, now: datetime) -> Mastery:
    """Met à jour la maîtrise d'une notion après une séance (§10.1).

    Première séance : on part de la boîte 1, donc une notion réussie du premier coup
    passe en boîte 2 (rappel à J+2).
    """
    rate = min(1.0, max(0.0, session_rate))
    if previous is None:
        score = _round(100 * rate)
        box, count = MIN_BOX, 1
    else:
        score = _round(0.6 * 100 * rate + 0.4 * previous.score)
        box, count = previous.box, previous.sessions_count + 1

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
    )


@dataclass(frozen=True)
class LessonReview:
    next_review_at: datetime | None
    mastered: bool


def lesson_review(masteries: Iterable[tuple[int, Mastery | None]]) -> LessonReview:
    """Prochaine révision d'une leçon (§10.2), à partir de (importance, maîtrise) de ses notions.

    Les notions jamais travaillées ne fixent pas de date : la prochaine séance les
    proposera en priorité (leur score vaut 0).
    """
    important = [(imp, m) for imp, m in masteries if imp >= IMPORTANT]
    practised = [m for _, m in important if m is not None]
    next_review = min((m.next_review_at for m in practised), default=None)
    mastered = bool(important) and all(
        m is not None and m.score >= KNOWN_SCORE and m.box == MAX_BOX for _, m in important
    )
    return LessonReview(next_review_at=next_review, mastered=mastered)
