"""Niveaux de maîtrise et répétition espacée.

Niveaux : 0 jamais vue, 1 découverte, 2 fragile, 3 en cours d'acquisition,
4 maîtrisée, 5 très bien maîtrisée. Après chaque séance, le niveau de chaque
notion travaillée évolue selon le taux de réussite, puis la prochaine révision
est programmée (J+1, J+2, J+4, J+7, J+14).
"""

from datetime import datetime, timedelta

MIN_LEVEL, MAX_LEVEL = 0, 5
REVIEW_INTERVAL_DAYS = {1: 1, 2: 2, 3: 4, 4: 7, 5: 14}

LEVEL_LABELS = {
    0: "jamais vue",
    1: "découverte",
    2: "fragile",
    3: "en cours d'acquisition",
    4: "maîtrisée",
    5: "très bien maîtrisée",
}


def next_level(level: int, success_rate: float) -> int:
    if level == 0:
        # Première rencontre : la notion est au moins « découverte ».
        return 3 if success_rate >= 0.8 else 2 if success_rate >= 0.5 else 1
    if success_rate >= 0.8:
        return min(MAX_LEVEL, level + 1)
    if success_rate < 0.5:
        return max(1, level - 1)
    return level


def next_review(level: int, now: datetime) -> datetime:
    return now + timedelta(days=REVIEW_INTERVAL_DAYS.get(level, 1))


def status(success_rate: float) -> str:
    """Statut affiché dans le bilan de fin de séance."""
    if success_rate >= 0.8:
        return "acquis"
    if success_rate >= 0.5:
        return "a_renforcer"
    return "a_revoir"


def target_difficulties(level: int) -> tuple[int, ...]:
    """Difficultés de question adaptées au niveau de maîtrise."""
    if level <= 1:
        return (1, 2)
    if level == 2:
        return (1, 2, 3)
    if level == 3:
        return (2, 3)
    return (3, 4)
