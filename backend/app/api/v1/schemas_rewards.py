"""Formats de la progression ludique (étape 20)."""

from datetime import datetime

from pydantic import BaseModel, Field


class BadgeOut(BaseModel):
    code: str
    emoji: str
    title: str
    how: str = Field(description="Comment le gagner.")
    earned_at: datetime | None = Field(None, description="null : pas encore gagné.")


class XpLineOut(BaseModel):
    label: str
    xp: int


class ProgressOut(BaseModel):
    """« ⭐ 120 XP · 🔥 Série : 4 jours » (accueil de l'enfant, tableau de bord du parent)."""

    total_xp: int
    level: int
    level_start_xp: int
    next_level_xp: int
    streak_days: int = Field(description="Jours d'affilée ; celle d'hier compte tant que la journée dure.")
    done_today: bool
    badges: list[BadgeOut] = Field(description="Tout le catalogue, gagnés d'abord.")


class RewardsOut(BaseModel):
    """Bilan de séance : ce que l'effort a rapporté (§86), jamais lié à la note."""

    xp: int
    lines: list[XpLineOut]
    message: str = Field(description="Le progrès le plus parlant de la séance (§39).")
    new_badges: list[BadgeOut]
    progress: ProgressOut
