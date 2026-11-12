"""Profil par notion pour le parent (§5.73, règles 1.17.0) : la décision qui découle des réponses.

Ce n'est pas une nouvelle décision du moteur : c'est, dit au parent, ce que le moteur fait déjà
de cette notion, avec le fait qui le justifie (§126, §131) :

- « Reprendre les bases » : notion découverte ou fragile (score sous 50) ; les séances proposent
  des activités faciles (reconnaître, se rappeler), puis le rappel de la règle après deux échecs ;
- « Exercices en plus » : notion en cours d'acquisition, ou réussie surtout avec une aide ; les
  séances visent le niveau de compréhension qui manque, sans aide ;
- « Révision espacée » : notion maîtrisée ; elle revient à la date prévue pour ne pas s'oublier.

Rien pour une notion jamais travaillée.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.mastery import Mastery
from app.domain.rules import RULES
from app.domain.state import NotionState
from app.domain.understanding import LEVEL_NAMES, CognitiveLevel, MasteryLevel, NotionLevel


class AdviceKind(StrEnum):
    BASICS = "basics"
    PRACTICE = "practice"
    SPACED = "spaced"


ADVICE_LABELS = {
    AdviceKind.BASICS: "Reprendre les bases",
    AdviceKind.PRACTICE: "Exercices en plus",
    AdviceKind.SPACED: "Révision espacée",
}


@dataclass(frozen=True)
class NotionAdvice:
    kind: AdviceKind
    why: str

    @property
    def label(self) -> str:
        return ADVICE_LABELS[self.kind]


def _day(moment: datetime) -> str:
    return f"{moment.day:02d}/{moment.month:02d}"


def _missing(level: NotionLevel) -> str | None:
    names = [LEVEL_NAMES[CognitiveLevel(m)] for m in sorted(level.missing)]
    return " et ".join(f"« {n} »" for n in names) or None


def notion_advice(
    level: NotionLevel, state: NotionState, mastery: Mastery | None, now: datetime
) -> NotionAdvice | None:
    if level.level == MasteryLevel.NEVER or mastery is None:
        return None
    if level.level <= MasteryLevel.FRAGILE:
        return NotionAdvice(
            AdviceKind.BASICS,
            f"Score de maîtrise {mastery.score}/100 : les séances reprennent avec des activités "
            "faciles (reconnaître, se rappeler) avant d'aller plus loin.",
        )
    helped = state.independence is not None and state.independence < RULES.profile.independence_below
    if level.level == MasteryLevel.LEARNING or helped:
        if helped:
            why = (
                f"Réussie surtout avec une aide ({round(100 * (state.independence or 0))} % seul) : "
                "les séances la reproposent pour qu'elle se fasse sans aide."
            )
        elif (missing := _missing(level)) is not None:
            why = f"Il reste à savoir {missing} : les séances proposent ce type d'exercice."
        else:
            why = f"Score de maîtrise {mastery.score}/100 : encore quelques exercices pour la fixer."
        return NotionAdvice(AdviceKind.PRACTICE, why)
    when = "dès la prochaine séance" if mastery.is_due(now) else f"le {_day(mastery.next_review_at)}"
    return NotionAdvice(
        AdviceKind.SPACED,
        f"Notion maîtrisée : prochaine révision {when}, de plus en plus espacée pour ne pas l'oublier.",
    )


def time_sentence(state: NotionState) -> str | None:
    """Temps de réponse habituel, signalé s'il est long (sans jugement : prendre son temps est permis)."""
    if state.median_seconds is None:
        return None
    sentence = f"Temps de réponse habituel : {state.median_seconds} s."
    if state.median_seconds > RULES.profile.slow_seconds:
        sentence += " C'est long : la notion demande encore de la réflexion."
    return sentence
