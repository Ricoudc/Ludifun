"""Ludi, le personnage qui accompagne la séance (§5.76) : un mot après chaque réponse.

Écrit par le code, jamais par l'IA : une phrase courte, à l'âge de l'enfant, qui dit quoi
regarder (« Tu y es presque ! Refais le calcul étape par étape. ») plutôt que « faux ». Le choix :

- réponse juste : un encouragement, plus marqué après une série (3, 5, 10 de suite), ou quand
  l'enfant réussit après une aide (« Tu as compris avec l'indice : bravo ») ;
- à moitié : « Tu y es presque », et ce qui manque ;
- fausse : le geste qui répond au type d'erreur (§5.34) ; sans type connu, un mot neutre ;
- jamais de reproche, jamais de « nul », de « faux » ou de comparaison avec d'autres enfants.

Trois tranches d'âge : CP-CE1 (mots très simples), CE2-CM2, collège (plus sobre). Le choix
entre plusieurs phrases équivalentes dépend de la position de l'activité : pas de hasard, la
même réponse donne la même phrase.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.domain.errors import ErrorType


class Age(StrEnum):
    YOUNG = "young"  # CP, CE1
    MIDDLE = "middle"  # CE2 à CM2
    COLLEGE = "college"  # 6e à 3e


def age_of(grade: str | None) -> Age:
    if grade in ("CP", "CE1"):
        return Age.YOUNG
    if grade in ("6e", "5e", "4e", "3e"):
        return Age.COLLEGE
    return Age.MIDDLE


class Mood(StrEnum):
    PROUD = "proud"  # 🥳 série ou réussite après une aide
    HAPPY = "happy"  # 😊 réponse juste
    CLOSE = "close"  # 🤏 presque
    THINKING = "thinking"  # 🤔 erreur : on regarde ensemble


@dataclass(frozen=True)
class CoachLine:
    mood: Mood
    message: str


STREAKS = (10, 5, 3)  # séries saluées

_HAPPY = {
    Age.YOUNG: ("Bravo !", "Super, c'est ça !", "Oui, bien joué !"),
    Age.MIDDLE: ("Bravo, c'est juste !", "Bien vu !", "Exactement !"),
    Age.COLLEGE: ("Juste.", "Bien vu.", "Exact, bien raisonné."),
}
_STREAK = {
    Age.YOUNG: "{n} de suite, tu es un champion !",
    Age.MIDDLE: "{n} bonnes réponses de suite, impressionnant !",
    Age.COLLEGE: "{n} de suite : c'est solide.",
}
_AFTER_HELP = {
    Age.YOUNG: "Tu as réussi avec l'indice, bravo ! La prochaine fois, tu le feras tout seul.",
    Age.MIDDLE: "Tu as compris grâce à l'aide : bravo. La prochaine fois, essaie sans.",
    Age.COLLEGE: "Réussi avec l'aide : la prochaine fois, essaie sans.",
}
_CLOSE = {
    Age.YOUNG: "Tu y es presque ! Regarde bien la correction.",
    Age.MIDDLE: "Tu y es presque ! Il ne manque pas grand-chose.",
    Age.COLLEGE: "Presque : regarde ce qui manque dans la correction.",
}
_NEUTRAL = {
    Age.YOUNG: "Ce n'est pas grave, on apprend en se trompant. Regarde la bonne réponse.",
    Age.MIDDLE: "Pas encore : lis la correction, elle va t'aider pour la suite.",
    Age.COLLEGE: "Pas cette fois : lis la correction, puis on continue.",
}
# Le geste qui répond à l'erreur (sans faire à la place de l'enfant).
_ERRORS: dict[ErrorType, dict[Age, str]] = {
    ErrorType.CALCULATION: {
        Age.YOUNG: "Tu y es presque ! Refais le calcul doucement, avec tes doigts si tu veux.",
        Age.MIDDLE: "Tu y es presque ! Refais le calcul étape par étape.",
        Age.COLLEGE: "Le raisonnement tient : vérifie le calcul, étape par étape.",
    },
    ErrorType.METHOD: {
        Age.YOUNG: "Regarde comment la leçon fait, puis essaie pareil.",
        Age.MIDDLE: "Regarde la méthode de la leçon : quelle est la première étape ?",
        Age.COLLEGE: "Ce n'est pas la bonne méthode : reprends celle de la leçon.",
    },
    ErrorType.READING: {
        Age.YOUNG: "Relis bien la question, doucement.",
        Age.MIDDLE: "Relis la question : que te demande-t-on exactement ?",
        Age.COLLEGE: "Relis l'énoncé : la question portait sur autre chose.",
    },
    ErrorType.CONFUSION: {
        Age.YOUNG: "Attention, ça se ressemble ! Regarde bien la différence.",
        Age.MIDDLE: "Attention : tu as pris une notion voisine. Regarde la différence.",
        Age.COLLEGE: "Confusion avec une notion proche : compare les deux.",
    },
    ErrorType.FORGOTTEN: {
        Age.YOUNG: "Ce n'est pas grave d'oublier ! Regarde la réponse, on la reverra.",
        Age.MIDDLE: "Ça s'oublie vite : lis la réponse, on la reverra bientôt.",
        Age.COLLEGE: "Oublié : relis la réponse, elle reviendra dans une prochaine séance.",
    },
    ErrorType.IMPRECISION: {
        Age.YOUNG: "Tu y es presque ! Regarde bien chaque lettre.",
        Age.MIDDLE: "Tu y es presque ! Vérifie l'orthographe et les accents.",
        Age.COLLEGE: "Presque : un détail (accent, unité, orthographe).",
    },
    ErrorType.RANDOM: {
        Age.YOUNG: "Prends ton temps, on n'est pas pressés !",
        Age.MIDDLE: "Pas si vite ! Prends le temps de réfléchir, ça compte plus que la vitesse.",
        Age.COLLEGE: "Trop rapide : prends le temps de réfléchir.",
    },
    ErrorType.STATEMENT: {
        Age.YOUNG: "Écoute bien la consigne : qu'est-ce qu'on te demande de faire ?",
        Age.MIDDLE: "Relis la consigne : que faut-il faire exactement ?",
        Age.COLLEGE: "Relis la consigne : la réponse attendue était d'une autre forme.",
    },
    ErrorType.KNOWLEDGE: {
        Age.YOUNG: "C'est nouveau, c'est normal ! Regarde la bonne réponse.",
        Age.MIDDLE: "Tu ne le savais pas encore : lis la correction, c'est comme ça qu'on apprend.",
        Age.COLLEGE: "Pas encore su : la correction te donne la règle.",
    },
}


def coach_line(
    result: str,
    *,
    grade: str | None,
    error: ErrorType | None = None,
    streak: int = 0,
    helped: bool = False,
    position: int = 0,
) -> CoachLine | None:
    """Le mot de Ludi après une réponse ; `streak` compte cette réponse ; None si passée."""
    age = age_of(grade)
    if result == "correct":
        if helped:
            return CoachLine(Mood.PROUD, _AFTER_HELP[age])
        if streak in STREAKS:
            return CoachLine(Mood.PROUD, _STREAK[age].format(n=streak))
        options = _HAPPY[age]
        return CoachLine(Mood.HAPPY, options[position % len(options)])
    if result == "partial":
        if error is not None and error in (ErrorType.IMPRECISION, ErrorType.CALCULATION):
            return CoachLine(Mood.CLOSE, _ERRORS[error][age])
        return CoachLine(Mood.CLOSE, _CLOSE[age])
    if result == "incorrect":
        if error is not None:
            return CoachLine(Mood.THINKING, _ERRORS[error][age])
        return CoachLine(Mood.THINKING, _NEUTRAL[age])
    return None
