"""État pédagogique d'une notion (cahier des charges §114, §129, §131).

Calculé à partir des réponses déjà enregistrées, sans rien demander de plus à l'enfant :

- un taux de réussite par niveau de compréhension (reconnaître, se rappeler, appliquer,
  expliquer, transférer), plutôt qu'un seul score ;
- l'autonomie : la part des réussites obtenues sans aide ;
- les faits récents, en une phrase chiffrée pour le parent (« Sur les 8 dernières activités :
  4 réussies seul, 2 avec une aide… »), distincts de l'interprétation du moteur.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.domain.errors import ERROR_LABELS, ErrorType
from app.domain.understanding import CognitiveLevel

RECENT = 8  # activités regardées pour la phrase du parent
PER_LEVEL = 10  # réponses regardées par niveau de compréhension
SUCCESS = 0.5  # à partir de là, la réponse compte comme (au moins en partie) réussie


@dataclass(frozen=True)
class Observation:
    """Une réponse portant sur la notion."""

    at: datetime
    level: int  # niveau de compréhension sollicité (1 à 5)
    result: float  # résultat pour la notion, déjà réduit par l'aide (0 à 1)
    score: float  # résultat brut de la réponse (0 à 1)
    help_level: int  # aide la plus forte demandée avant la réponse (0 : seul)
    error_type: str | None = None


@dataclass(frozen=True)
class NotionState:
    level_rates: dict[int, float | None]  # niveau de compréhension → taux de réussite
    independence: float | None  # part des réussites obtenues sans aide ; None : aucune réussite
    alone: int  # parmi les RECENT dernières : réussies sans aide
    helped: int  # réussies avec une aide
    partial: int  # à moitié, sans aide
    failed: int
    main_error: tuple[str, int] | None  # erreur la plus fréquente récemment (libellé, nombre)

    @property
    def recent(self) -> int:
        return self.alone + self.helped + self.partial + self.failed


def _error_label(code: str) -> str:
    try:
        return ERROR_LABELS[ErrorType(code)]
    except ValueError:
        return code


def notion_state(observations: Sequence[Observation]) -> NotionState:
    ordered = sorted(observations, key=lambda o: o.at)
    rates: dict[int, float | None] = {}
    for level in CognitiveLevel:
        at_level = [o.result for o in ordered if o.level == level][-PER_LEVEL:]
        rates[int(level)] = round(sum(at_level) / len(at_level), 2) if at_level else None

    successes = [o for o in ordered if o.score >= SUCCESS]
    independence = (
        round(sum(1 for o in successes if o.help_level == 0) / len(successes), 2) if successes else None
    )

    recent = ordered[-RECENT:]
    alone = sum(1 for o in recent if o.score >= 1 and o.help_level == 0)
    helped = sum(1 for o in recent if o.score >= SUCCESS and o.help_level > 0)
    partial = sum(1 for o in recent if SUCCESS <= o.score < 1 and o.help_level == 0)
    failed = sum(1 for o in recent if o.score < SUCCESS)
    errors = Counter(o.error_type for o in recent if o.error_type)
    main_error = None
    if errors:
        code, count = errors.most_common(1)[0]
        main_error = (_error_label(code), count)
    return NotionState(rates, independence, alone, helped, partial, failed, main_error)


def facts_sentence(state: NotionState) -> str | None:
    """Ce qui a été observé, chiffré, sans interprétation (§131) ; None si rien encore."""
    if state.recent == 0:
        return None
    parts = [
        f"{state.alone} réussie{'s' if state.alone > 1 else ''} seul" if state.alone else "",
        f"{state.helped} avec une aide" if state.helped else "",
        f"{state.partial} à moitié" if state.partial else "",
        f"{state.failed} ratée{'s' if state.failed > 1 else ''}" if state.failed else "",
    ]
    counted = ", ".join(p for p in parts if p)
    what = "la dernière activité" if state.recent == 1 else f"les {state.recent} dernières activités"
    sentence = f"Sur {what} : {counted}."
    if state.main_error is not None and state.main_error[1] >= 2:
        label, count = state.main_error
        sentence += f" Erreur la plus fréquente : {label.lower()} ({count} fois)."
    return sentence
