"""Types d'erreurs et erreurs récurrentes (cahier des charges complet §43, §62-§63 ;
spécification technique §5.5).

Une réponse ratée ne dit pas seulement « faux » : elle dit *pourquoi*, autant qu'on peut le
savoir sans deviner. Le type vient de l'activité elle-même (le distracteur choisi, une réponse
presque juste, une carte « je ne savais pas »…) ou, pour une question ouverte, de l'évaluateur.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.rules import RULES
from app.domain.text import damerau_levenshtein, normalize


class ErrorType(StrEnum):
    KNOWLEDGE = "knowledge"  # ne connaît pas encore
    CALCULATION = "calculation"  # erreur de calcul
    METHOD = "method"  # mauvaise méthode
    READING = "reading"  # a mal lu l'énoncé
    CONFUSION = "confusion"  # confond avec une autre notion
    FORGOTTEN = "forgotten"  # ne s'en souvient pas (réponse vide, « je ne savais pas »)
    IMPRECISION = "imprecision"  # presque : une faute, un détail
    RANDOM = "random"  # répond trop vite, au hasard
    STATEMENT = "statement"  # a mal compris la consigne


# Libellés pour le parent : ce que l'erreur dit de l'enfant, sans jugement.
ERROR_LABELS = {
    ErrorType.KNOWLEDGE: "Ne connaît pas encore",
    ErrorType.CALCULATION: "Erreur de calcul",
    ErrorType.METHOD: "Se trompe de méthode",
    ErrorType.READING: "Lit trop vite l'énoncé",
    ErrorType.CONFUSION: "Confond avec une autre notion",
    ErrorType.FORGOTTEN: "Ne s'en souvient pas",
    ErrorType.IMPRECISION: "Presque : une faute ou un détail",
    ErrorType.RANDOM: "Répond trop vite, au hasard",
    ErrorType.STATEMENT: "Comprend mal la consigne",
}

RANDOM_BELOW_MS = RULES.adaptation.random_below_ms  # réponse fausse plus rapide : au hasard
RECURRING_SESSIONS = RULES.adaptation.recurring_sessions  # même erreur dans N séances : récurrente
_EMPTY_ANSWERS = {"", "?", "je ne sais pas", "je sais pas", "sais pas", "aucune idee", "jsp"}


def written_answer_error(given: str, answers: Iterable[str]) -> ErrorType:
    """Réponse écrite fausse (texte à trous) : vide, presque juste, ou inconnue."""
    text = normalize(given)
    if text in _EMPTY_ANSWERS:
        return ErrorType.FORGOTTEN
    for answer in answers:
        expected = normalize(answer)
        if expected and damerau_levenshtein(text, expected) <= max(2, len(expected) // 3):
            return ErrorType.IMPRECISION
    return ErrorType.KNOWLEDGE


def with_speed(error: ErrorType, duration_ms: int | None) -> ErrorType:
    """Une réponse fausse donnée en moins d'une seconde et demie : au hasard, quelle qu'elle soit."""
    if duration_ms is not None and duration_ms < RANDOM_BELOW_MS:
        return ErrorType.RANDOM
    return error


@dataclass(frozen=True)
class ErrorOccurrence:
    knowledge_id: str
    error_type: ErrorType
    session_id: str
    at: datetime


@dataclass(frozen=True)
class RecurringError:
    knowledge_id: str
    error_type: ErrorType
    sessions: int
    last_at: datetime


def recurring_errors(occurrences: Iterable[ErrorOccurrence]) -> list[RecurringError]:
    """Même type d'erreur sur la même notion dans au moins 3 séances distinctes, les plus
    fréquentes puis les plus récentes d'abord. Les réponses au hasard n'en sont pas : elles
    disent quelque chose de l'attention, pas de la notion."""
    sessions: dict[tuple[str, ErrorType], set[str]] = defaultdict(set)
    last: dict[tuple[str, ErrorType], datetime] = {}
    for o in occurrences:
        if o.error_type is ErrorType.RANDOM:
            continue
        key = (o.knowledge_id, o.error_type)
        sessions[key].add(o.session_id)
        last[key] = max(last.get(key, o.at), o.at)
    found = [
        RecurringError(knowledge_id, error_type, len(ids), last[(knowledge_id, error_type)])
        for (knowledge_id, error_type), ids in sessions.items()
        if len(ids) >= RECURRING_SESSIONS
    ]
    return sorted(found, key=lambda r: (-r.sessions, -r.last_at.timestamp(), r.knowledge_id))
