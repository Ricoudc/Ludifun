"""Raison de chaque décision du moteur (cahier des charges §126) : pourquoi cette activité, cette
remédiation, cette pause. Une règle nommée et les faits qui l'ont déclenchée, enregistrés avec la
décision et la version du moteur, puis traduits en une phrase pour le parent."""

from enum import StrEnum
from typing import Any

from app.domain.understanding import LEVEL_NAMES, CognitiveLevel


class Rule(StrEnum):
    FIRST_SESSION = "first_session"  # première séance : les notions les plus importantes d'abord
    NEW_NOTION = "new_notion"  # notion jamais travaillée
    LEVEL_UP = "level_up"  # score suffisant : le niveau de compréhension manquant
    DEEPEN = "deepen"  # notion maîtrisée : expliquer ou transférer
    BY_SCORE = "by_score"  # révision : difficulté selon le score
    GAME = "game"  # jeu sur plusieurs notions
    SPEED = "speed"  # défi rapide
    REPLAY = "replay"  # reprise d'une erreur de la séance
    REMEDIATION = "remediation"  # échecs répétés : rappel puis activités plus faciles
    BONUS = "bonus"  # séance rapide et réussie : défis plus difficiles
    ERRORS_SESSION = "errors_session"  # « Revoir mes erreurs »
    PAUSE_FAST_GUESSING = "pause_fast_guessing"  # réponses au hasard : pause proposée
    PAUSE_STRUGGLING = "pause_struggling"  # échecs d'affilée : pause proposée


Reason = dict[str, Any]


def reason(rule: Rule, **facts: Any) -> Reason:
    return {"rule": rule.value, "facts": facts}


def _level(value: Any) -> str:
    try:
        return LEVEL_NAMES[CognitiveLevel(int(value))]
    except (TypeError, ValueError, KeyError):
        return "?"


def describe(decision: Reason | None) -> str | None:
    """La décision en une phrase, avec ses faits (pas d'interprétation)."""
    if not decision:
        return None
    f: dict[str, Any] = decision.get("facts", {})
    match decision.get("rule"):
        case Rule.FIRST_SESSION:
            return (
                f"Première séance : notion d'importance {f.get('importance')}/5, "
                f"difficulté {f.get('difficulty')}."
            )
        case Rule.NEW_NOTION:
            return "Notion encore jamais travaillée."
        case Rule.LEVEL_UP:
            return (
                f"Score {f.get('score')} ≥ {f.get('threshold')} : il reste à valider le niveau "
                f"« {_level(f.get('level'))} »."
            )
        case Rule.DEEPEN:
            return (
                f"Notion maîtrisée (score {f.get('score')}) : approfondir, "
                f"niveau « {_level(f.get('level'))} »."
            )
        case Rule.BY_SCORE:
            due = "révision prévue aujourd'hui" if f.get("due") else "notion à consolider"
            return f"{due.capitalize()} (score {f.get('score')}) : difficulté {f.get('difficulty')}."
        case Rule.GAME:
            return f"Jeu sur {f.get('notions')} notions de la leçon."
        case Rule.SPEED:
            return f"Défi rapide sur {f.get('notions')} notion(s)."
        case Rule.REPLAY:
            return "Notion ratée pendant la séance : reprise dans un autre format."
        case Rule.REMEDIATION:
            return (
                f"{f.get('failures')} échecs sur cette notion dans la séance : "
                "rappel puis activité plus facile."
            )
        case Rule.BONUS:
            return (
                f"Séance réussie à {round(100 * float(f.get('average', 0)))} % et rapide : "
                "défi plus difficile."
            )
        case Rule.ERRORS_SESSION:
            return "Séance « Revoir mes erreurs » : notion ratée lors d'une séance précédente."
        case Rule.PAUSE_FAST_GUESSING:
            return (
                f"{f.get('fast_wrong')} réponses fausses très rapides sur les {f.get('window')} "
                "dernières : pause proposée."
            )
        case Rule.PAUSE_STRUGGLING:
            return f"{f.get('failures')} échecs d'affilée : pause proposée."
    return None
