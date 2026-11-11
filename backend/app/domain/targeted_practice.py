"""Exercice neuf sur une erreur qui revient (§5.74, CDC §118, règles 1.18.0).

Le matériel d'une notion est produit une fois, à l'analyse. Quand la même erreur revient sur une
notion (même type d'erreur dans `adaptation.recurring_sessions` séances, `errors.recurring_errors`),
l'IA propose 1 ou 2 questions neuves qui visent CETTE erreur : le piège dans lequel l'enfant
tombe devient un des distracteurs, et la correction le montre. Le code ne garde une question que :

- si elle passe les contrôles des questions de la leçon (réponse absente de l'énoncé, trois
  distracteurs distincts de même nature, rien qui renvoie à une fiche absente) ;
- si sa bonne réponse est prouvée : présente dans la notion telle que la leçon l'enseigne, ou,
  en maths, un calcul de l'énoncé dont le code retrouve lui-même le résultat. Le reste
  (« la mémoire de l'IA ») est écarté ;
- si elle n'a rien d'inadapté à un enfant (§141), et n'est pas déjà dans la leçon (vérifié par
  l'appelant, `app.domain.duplicates`).

Une notion n'est ciblée qu'une fois par type d'erreur (la question gardée porte `target_error`) ;
au plus `targeted.notions` notions par séance terminée, pour borner le coût. Le QCM propose
ensuite ces questions en priorité (`targeted.share`), et la correction dit pourquoi.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.domain.child_safety import unsafe_reason
from app.domain.equivalence import same_answer, value_of
from app.domain.errors import ERROR_LABELS, ErrorType, RecurringError
from app.domain.knowledge import KnowledgeUnit, MaterialQuestion
from app.domain.rules import RULES
from app.domain.text import contains_words, fuzzy_contains
from app.domain.validation import (
    PICTURE_REASON,
    SUPPORT_REASON,
    Rejection,
    check_question,
    needs_picture,
    needs_support,
)

NOTIONS = RULES.targeted.notions  # notions ciblées au plus, par séance terminée
PER_ERROR = RULES.targeted.per_error  # questions gardées au plus, par notion et par erreur
SHARE = RULES.targeted.share  # part des QCM d'une notion tirés de ses questions ciblées

# « 7 × 8 », « 45 - 18 », « 3,5 + 1,2 » dans un énoncé : un seul calcul, vérifiable par le code.
_CALCULATION = re.compile(r"\d+(?:[,.]\d+)?(?:\s*[+\-−–×x*÷:/]\s*\d+(?:[,.]\d+)?)+")

# Ce que l'IA doit viser, pour chaque erreur (sans jugement sur l'enfant).
ERROR_TARGETS: dict[ErrorType, str] = {
    ErrorType.KNOWLEDGE: "l'enfant ne connaît pas encore bien ce que dit la leçon",
    ErrorType.CALCULATION: "l'enfant se trompe dans les calculs (retenues, tables, signes)",
    ErrorType.METHOD: "l'enfant applique une mauvaise méthode",
    ErrorType.READING: "l'enfant lit l'énoncé trop vite et répond à une autre question",
    ErrorType.CONFUSION: "l'enfant confond cette notion avec une notion voisine",
    ErrorType.FORGOTTEN: "l'enfant oublie ce que dit la leçon",
    ErrorType.IMPRECISION: "l'enfant sait presque : une faute, un accent, une unité",
    ErrorType.STATEMENT: "l'enfant comprend mal la consigne",
}


@dataclass(frozen=True)
class Target:
    unit: KnowledgeUnit
    error: ErrorType

    @property
    def label(self) -> str:
        return ERROR_LABELS[self.error]


def targets(
    recurring: Sequence[RecurringError], units: Sequence[KnowledgeUnit], limit: int = NOTIONS
) -> list[Target]:
    """Les erreurs récurrentes à cibler : sur une notion de la leçon, pas encore ciblées pour
    cette erreur, une par notion (la plus fréquente), au plus `limit`."""
    by_key = {u.id: u for u in units}
    chosen: list[Target] = []
    for r in recurring:  # déjà dans l'ordre : les plus fréquentes, puis les plus récentes
        unit = by_key.get(r.knowledge_id)
        if unit is None or r.error_type not in ERROR_TARGETS or any(t.unit.id == unit.id for t in chosen):
            continue
        if any(q.target_error == r.error_type for q in unit.material.questions):
            continue  # déjà un exercice neuf pour cette erreur
        chosen.append(Target(unit, r.error_type))
        if len(chosen) >= limit:
            break
    return chosen


@dataclass(frozen=True)
class ProposedTarget:
    """Ce que l'IA propose : une question à choix ; `trap` est le distracteur où mène l'erreur."""

    stem: str
    answer: str
    distractors: list[str]
    difficulty: int
    trap: str | None = None
    why: str = ""  # en une phrase pour l'enfant : pourquoi le piège est faux


@dataclass(frozen=True)
class CheckedTargets:
    questions: list[MaterialQuestion] = field(default_factory=list)
    rejected: list[Rejection] = field(default_factory=list)


def _proved(question: MaterialQuestion, unit: KnowledgeUnit) -> bool:
    """La bonne réponse vient de la leçon, ou d'un calcul que le code refait."""
    corpus = f"{unit.item.corpus()} {' '.join(q.answer for q in unit.material.questions)}"
    if contains_words(corpus, question.answer) or fuzzy_contains(corpus, question.answer):
        return True
    expected = value_of(question.answer)
    calculations = _CALCULATION.findall(question.stem)
    return expected is not None and len(calculations) == 1 and value_of(calculations[0]) == expected


def check_targets(
    target: Target, proposed: Sequence[ProposedTarget], limit: int = PER_ERROR
) -> CheckedTargets:
    kept: list[MaterialQuestion] = []
    rejected: list[Rejection] = []
    context = target.unit.item.corpus()
    for i, p in enumerate(proposed):
        label = f"targeted[{i}]"
        trap = p.trap if p.trap and any(same_answer(p.trap, d) for d in p.distractors) else None
        if trap is None:
            rejected.append(Rejection(label, "le piège ciblé ne correspond à aucun distracteur"))
            continue
        why = p.why.strip()
        if not why:
            rejected.append(Rejection(label, "explication du piège manquante"))
            continue
        question, reason = check_question(
            {
                "difficulty": min(max(p.difficulty, 1), 2),
                "stem": p.stem,
                "answer": p.answer,
                "distractors": [
                    {
                        "text": d,
                        "misconception": target.error.value if trap and same_answer(d, trap) else None,
                    }
                    for d in p.distractors
                ],
            }
        )
        if question is not None:
            if needs_picture(question.stem):
                reason = PICTURE_REASON
            elif needs_support(question.stem):
                reason = SUPPORT_REASON
            elif not _proved(question, target.unit):
                reason = "bonne réponse ni dans la leçon ni dans un calcul vérifié"
            elif unsafe := unsafe_reason(
                [question.stem, question.answer, *question.distractors, p.why], context
            ):
                reason = unsafe
            elif len(kept) >= limit:
                reason = f"plus de {limit} questions pour cette erreur"
        if question is None or reason:
            rejected.append(Rejection(label, reason))
            continue
        kept.append(
            question.model_copy(
                update={"target_error": target.error.value, "target_why": why}
            )
        )
    return CheckedTargets(kept, rejected)
