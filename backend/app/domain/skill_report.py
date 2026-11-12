"""Bilan d'une compétence pour le parent (spécification technique §5.52).

Pour chaque compétence d'une leçon : où en est l'enfant (statut tiré du niveau déjà calculé par
le moteur, aucun nouveau seuil), ce qui a été observé sur ses notions (chiffres cumulés, §131),
la notion qui freine, et un conseil concret à faire à la maison, choisi selon ce que la
compétence demande (se rappeler, appliquer, expliquer…) et l'erreur la plus fréquente.

Domaine pur : pas de base, pas d'IA ; les phrases sont écrites ici, jamais générées.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.domain.errors import ERROR_LABELS, ErrorType
from app.domain.knowledge import SkillVerb
from app.domain.state import NotionState
from app.domain.understanding import MasteryLevel, NotionLevel


class SkillStatus(StrEnum):
    NOT_STARTED = "not_started"  # aucune activité encore
    TO_WORK = "to_work"  # découverte ou fragile
    IN_PROGRESS = "in_progress"  # en cours d'acquisition
    ACQUIRED = "acquired"  # maîtrisée ou très bien maîtrisée


@dataclass(frozen=True)
class SkillNotion:
    label: str
    level: NotionLevel
    state: NotionState


@dataclass(frozen=True)
class SkillReport:
    status: SkillStatus
    summary: str  # une phrase : où en est l'enfant
    facts: str | None  # chiffres cumulés sur les notions de la compétence ; None : rien observé
    weakest: str | None  # la notion qui freine ; None si la compétence est acquise
    advice: str | None  # quoi faire à la maison ; None si tout est acquis ou rien commencé


def status_of(level: MasteryLevel, observed: bool) -> SkillStatus:
    if level >= MasteryLevel.MASTERED:
        return SkillStatus.ACQUIRED
    if level == MasteryLevel.LEARNING:
        return SkillStatus.IN_PROGRESS
    return SkillStatus.TO_WORK if observed or level > MasteryLevel.NEVER else SkillStatus.NOT_STARTED


_SUMMARY = {
    SkillStatus.NOT_STARTED: "Pas encore travaillée : elle viendra dans les prochaines séances.",
    SkillStatus.TO_WORK: "À travailler : les bases ne sont pas encore en place.",
    SkillStatus.IN_PROGRESS: "En bonne voie : c'est presque acquis, il reste à consolider.",
    SkillStatus.ACQUIRED: "Acquise : réussie seul, et retenue.",
}

# Conseil selon ce que la compétence demande ; « {notion} » : la notion qui freine.
_BY_VERB = {
    SkillVerb.RECOGNIZE: "Montrez « {notion} » au milieu d'autres choses et demandez de le retrouver.",
    SkillVerb.RECALL: (
        "Faites redire « {notion} » sans regarder la leçon, aujourd'hui puis dans trois jours."
    ),
    SkillVerb.APPLY: "Proposez un petit exercice où il faut se servir de « {notion} », sans la leçon.",
    SkillVerb.EXPLAIN: "Demandez d'expliquer « {notion} » avec ses propres mots, comme à un plus petit.",
    SkillVerb.TRANSFER: "Cherchez ensemble « {notion} » dans une situation de tous les jours.",
}

# Complément selon l'erreur la plus fréquente (au moins 2 fois récemment).
_BY_ERROR = {
    ErrorType.CALCULATION: "Les erreurs viennent surtout du calcul : poser l'opération et vérifier aide.",
    ErrorType.METHOD: "Les erreurs viennent surtout de la méthode : redire les étapes dans l'ordre.",
    ErrorType.READING: (
        "Les erreurs viennent surtout d'une lecture trop rapide : relire la consigne à voix haute."
    ),
    ErrorType.STATEMENT: "La consigne est souvent mal comprise : la faire reformuler avant de répondre.",
    ErrorType.CONFUSION: "Deux notions se mélangent : les comparer côte à côte.",
    ErrorType.FORGOTTEN: (
        "C'est surtout un oubli : revoir un peu chaque jour vaut mieux qu'une fois longtemps."
    ),
    ErrorType.KNOWLEDGE: "La notion n'est pas encore connue : relire la leçon ensemble d'abord.",
    ErrorType.IMPRECISION: "C'est presque juste : un détail ou une faute à surveiller.",
    ErrorType.RANDOM: "Les réponses vont parfois trop vite : prendre le temps de lire avant de toucher.",
}
_ERROR_OF_LABEL = {label: code for code, label in ERROR_LABELS.items()}


def _facts(states: Sequence[NotionState]) -> str | None:
    alone = sum(s.alone for s in states)
    helped = sum(s.helped for s in states)
    partial = sum(s.partial for s in states)
    failed = sum(s.failed for s in states)
    total = alone + helped + partial + failed
    if total == 0:
        return None
    parts = [
        f"{alone} réussie{'s' if alone > 1 else ''} seul" if alone else "",
        f"{helped} avec une aide" if helped else "",
        f"{partial} à moitié" if partial else "",
        f"{failed} ratée{'s' if failed > 1 else ''}" if failed else "",
    ]
    what = "la dernière activité" if total == 1 else f"les {total} dernières activités"
    return f"Sur {what} de ses notions : {', '.join(p for p in parts if p)}."


def _main_error(states: Sequence[NotionState]) -> ErrorType | None:
    counts: Counter[str] = Counter()
    for state in states:
        if state.main_error is not None:
            counts[state.main_error[0]] += state.main_error[1]
    if not counts:
        return None
    label, count = counts.most_common(1)[0]
    return _ERROR_OF_LABEL.get(label) if count >= 2 else None


def _weakest(notions: Sequence[SkillNotion]) -> SkillNotion | None:
    """La notion la plus basse ; à niveau égal, celle qui a le plus d'échecs récents."""
    if not notions:
        return None
    return min(notions, key=lambda n: (n.level.level, -n.state.failed))


def skill_report(verb: SkillVerb, level: MasteryLevel, notions: Sequence[SkillNotion]) -> SkillReport:
    states = [n.state for n in notions]
    facts = _facts(states)
    status = status_of(level, facts is not None)
    weakest = _weakest(notions) if status in (SkillStatus.TO_WORK, SkillStatus.IN_PROGRESS) else None
    advice = None
    if weakest is not None:
        advice = _BY_VERB[verb].format(notion=weakest.label)
        if (error := _main_error(states)) is not None:
            advice += " " + _BY_ERROR[error]
    return SkillReport(
        status=status,
        summary=_SUMMARY[status],
        facts=facts,
        weakest=weakest.label if weakest is not None else None,
        advice=advice,
    )
