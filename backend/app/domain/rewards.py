"""Missions et gamification (cahier des charges complet §37 à §40, §86 ; spécification technique
§5.10, étape 20).

Les récompenses valorisent l'effort, la progression, la persévérance, la régularité et la
compréhension (§39), jamais la note : une séance difficile rapporte autant qu'une séance
réussie, et demander de l'aide ne fait rien perdre. Rien ne se perd non plus : l'XP ne baisse
jamais, une série interrompue recommence sans reproche, un badge gagné reste gagné. Aucune
comparaison entre enfants.

Tout est déterministe et calculé à la clôture de la séance.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

DAILY_XP_CAP = 150  # au-delà, l'XP du jour n'augmente plus : réviser plus n'est pas mieux
MAX_ACTIVITY_XP = 20
MAX_COMEBACKS = 3
SUCCESS = 0.8  # taux de réussite d'une notion pendant la séance pour parler de « réussite »


# --------------------------------------------------------------------------- #
# Ce qui s'est passé pendant la séance
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SessionFacts:
    """Faits de la séance close, rassemblés par le service (aucune note)."""

    answered: int  # activités faites (reprise, rappel et défis bonus compris)
    level_ups: list[str]  # notions qui ont gagné un niveau
    comebacks: list[str]  # notions ratées avant, réussies aujourd'hui
    newly_mastered: list[str]  # notions qui atteignent le niveau 4 pour la première fois
    remediation: bool  # un rappel de la règle a été inséré, et la séance est allée au bout
    reviewed_errors: bool  # reprise des erreurs faite, ou séance « Revoir mes erreurs »
    bonus: bool  # défis bonus acceptés
    success_after_help: bool  # une activité réussie après « Je n'ai pas compris »
    open_question_success: bool  # une réponse rédigée juste
    lesson_mastered: bool
    first_of_day: bool  # première séance terminée de la journée
    streak_days: int  # série après cette séance
    sessions_completed: int  # séances terminées, celle-ci comprise
    xp_today_before: int  # XP déjà gagnée aujourd'hui


# --------------------------------------------------------------------------- #
# XP
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class XpLine:
    label: str
    xp: int


def session_xp(facts: SessionFacts) -> list[XpLine]:
    """Le détail de l'XP gagnée (§86 « XP : +35 »), plafonné par jour."""
    lines = [XpLine("Séance terminée", 10)]
    if facts.answered:
        lines.append(XpLine("Activités faites", min(facts.answered, MAX_ACTIVITY_XP)))
    if facts.level_ups:
        lines.append(XpLine("Notions en progrès", 5 * len(facts.level_ups)))
    if facts.comebacks:
        lines.append(XpLine("Notions enfin réussies", 10 * min(len(facts.comebacks), MAX_COMEBACKS)))
    if facts.remediation:
        lines.append(XpLine("Tu n'as rien lâché", 5))
    if facts.success_after_help:
        lines.append(XpLine("Aide bien utilisée", 5))
    if facts.reviewed_errors:
        lines.append(XpLine("Erreurs revues", 5))
    if facts.bonus:
        lines.append(XpLine("Défis bonus", 5))
    if facts.first_of_day and facts.streak_days >= 2:
        lines.append(XpLine("Régularité", 5))
    room = max(0, DAILY_XP_CAP - facts.xp_today_before)
    capped: list[XpLine] = []
    for line in lines:
        xp = min(line.xp, room)
        room -= xp
        if xp:
            capped.append(XpLine(line.label, xp))
    return capped


# --------------------------------------------------------------------------- #
# Niveaux
# --------------------------------------------------------------------------- #


def level_start(level: int) -> int:
    """XP nécessaire pour atteindre un niveau : 0, 100, 300, 600, 1000, 1500…"""
    return 50 * level * (level - 1)


@dataclass(frozen=True)
class PlayerLevel:
    level: int
    start_xp: int
    next_xp: int

    def progress(self, total_xp: int) -> float:
        return (total_xp - self.start_xp) / (self.next_xp - self.start_xp)


def player_level(total_xp: int) -> PlayerLevel:
    level = 1
    while level_start(level + 1) <= total_xp:
        level += 1
    return PlayerLevel(level, level_start(level), level_start(level + 1))


# --------------------------------------------------------------------------- #
# Série
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Streak:
    days: int
    done_today: bool


def streak(days: Iterable[date], today: date) -> Streak:
    """Jours d'affilée avec au moins une séance terminée. Tant que la journée n'est pas finie, la
    série d'hier reste en cours (pas de pression à réviser tôt)."""
    worked = set(days)
    done_today = today in worked
    day = today if done_today else today - timedelta(days=1)
    count = 0
    while day in worked:
        count += 1
        day -= timedelta(days=1)
    return Streak(count, done_today)


# --------------------------------------------------------------------------- #
# Badges
# --------------------------------------------------------------------------- #


class BadgeCode(StrEnum):
    FIRST_SESSION = "first_session"
    SESSIONS_10 = "sessions_10"
    SESSIONS_50 = "sessions_50"
    STREAK_3 = "streak_3"
    STREAK_7 = "streak_7"
    COMEBACK = "comeback"
    PERSEVERING = "persevering"
    HELP_USED = "help_used"
    ERRORS_REVIEWED = "errors_reviewed"
    EXPLAINER = "explainer"
    NOTION_MASTERED = "notion_mastered"
    LESSON_MASTERED = "lesson_mastered"
    BONUS = "bonus"


@dataclass(frozen=True)
class Badge:
    code: BadgeCode
    emoji: str
    title: str
    how: str  # comment le gagner, montré tant qu'il n'est pas gagné


BADGES = [
    Badge(BadgeCode.FIRST_SESSION, "🌱", "Premier pas", "Termine ta première séance."),
    Badge(BadgeCode.STREAK_3, "🔥", "Trois jours de suite", "Révise trois jours d'affilée."),
    Badge(BadgeCode.COMEBACK, "🏆", "Revanche", "Réussis une notion qui te posait problème."),
    Badge(BadgeCode.HELP_USED, "❓", "Curieux", "Réussis une activité après avoir demandé de l'aide."),
    Badge(BadgeCode.ERRORS_REVIEWED, "🔄", "Sans peur des erreurs", "Revois tes erreurs après une séance."),
    Badge(BadgeCode.PERSEVERING, "💪", "Persévérant", "Va au bout d'une séance après un rappel de la règle."),
    Badge(BadgeCode.EXPLAINER, "🗣️", "Bien expliqué", "Réponds juste à une question à rédiger."),
    Badge(BadgeCode.NOTION_MASTERED, "⭐", "Notion maîtrisée", "Maîtrise une notion (niveau 4)."),
    Badge(BadgeCode.BONUS, "🚀", "Toujours plus", "Relève les défis bonus."),
    Badge(BadgeCode.SESSIONS_10, "📚", "Habitué", "Termine dix séances."),
    Badge(BadgeCode.STREAK_7, "🌟", "Une semaine de suite", "Révise sept jours d'affilée."),
    Badge(BadgeCode.LESSON_MASTERED, "🏅", "Leçon maîtrisée", "Maîtrise toutes les notions d'une leçon."),
    Badge(BadgeCode.SESSIONS_50, "🏛️", "Pilier de la révision", "Termine cinquante séances."),
]
BADGE_BY_CODE = {b.code: b for b in BADGES}


def earned_badges(facts: SessionFacts, already: Iterable[str]) -> list[Badge]:
    """Badges gagnés par cette séance (chacun une seule fois), dans l'ordre du catalogue."""
    reached = {
        BadgeCode.FIRST_SESSION: facts.sessions_completed >= 1,
        BadgeCode.SESSIONS_10: facts.sessions_completed >= 10,
        BadgeCode.SESSIONS_50: facts.sessions_completed >= 50,
        BadgeCode.STREAK_3: facts.streak_days >= 3,
        BadgeCode.STREAK_7: facts.streak_days >= 7,
        BadgeCode.COMEBACK: bool(facts.comebacks),
        BadgeCode.PERSEVERING: facts.remediation,
        BadgeCode.HELP_USED: facts.success_after_help,
        BadgeCode.ERRORS_REVIEWED: facts.reviewed_errors,
        BadgeCode.EXPLAINER: facts.open_question_success,
        BadgeCode.NOTION_MASTERED: bool(facts.newly_mastered),
        BadgeCode.LESSON_MASTERED: facts.lesson_mastered,
        BadgeCode.BONUS: facts.bonus,
    }
    owned = set(already)
    return [b for b in BADGES if reached[b.code] and b.code not in owned]


# --------------------------------------------------------------------------- #
# Message du bilan (§39)
# --------------------------------------------------------------------------- #


class Cheer(StrEnum):
    COMEBACK = "comeback"
    MASTERED = "mastered"
    LEVEL_UP = "level_up"
    PERSEVERED = "persevered"
    STREAK = "streak"
    EFFORT = "effort"


@dataclass(frozen=True)
class Encouragement:
    kind: Cheer
    knowledge_id: str | None = None


def encouragement(facts: SessionFacts) -> Encouragement:
    """Le progrès le plus parlant de la séance, plutôt qu'une note (« Tu as réussi une notion qui
    te posait problème ! » plutôt que « 10/10 »)."""
    if facts.comebacks:
        return Encouragement(Cheer.COMEBACK, facts.comebacks[0])
    if facts.newly_mastered:
        return Encouragement(Cheer.MASTERED, facts.newly_mastered[0])
    if facts.level_ups:
        return Encouragement(Cheer.LEVEL_UP, facts.level_ups[0])
    if facts.remediation:
        return Encouragement(Cheer.PERSEVERED)
    if facts.first_of_day and facts.streak_days >= 2:
        return Encouragement(Cheer.STREAK)
    return Encouragement(Cheer.EFFORT)


def cheer_text(cheer: Encouragement, label: str | None, streak_days: int) -> str:
    match cheer.kind:
        case Cheer.COMEBACK:
            return f"🏆 Tu as réussi une notion qui te posait problème : {label} !"
        case Cheer.MASTERED:
            return f"⭐ Tu maîtrises maintenant : {label} !"
        case Cheer.LEVEL_UP:
            return f"⬆️ Tu progresses sur : {label} !"
        case Cheer.PERSEVERED:
            return "💪 Ce n'était pas facile, et tu as tenu jusqu'au bout. Bravo !"
        case Cheer.STREAK:
            return f"🔥 {streak_days} jours de suite : ta régularité paie !"
        case Cheer.EFFORT:
            return "🎉 Bravo pour ton travail : chaque séance compte !"
