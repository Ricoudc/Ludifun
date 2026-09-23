"""Notation d'une séance (cahier des charges §9).

Le score d'une activité est calculé par l'activité elle-même (`ActivityType.grade`).
Ici : les preuves de maîtrise par notion, la note sur 10 et le bilan de fin de séance.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.activities.base import ActivityCode, BuiltActivity, Grade
from app.domain.activities.registry import ActivityRegistry
from app.domain.mastery import FRAGILE_RATE, MASTERED_RATE, Mastery, lesson_review, update_mastery

DIFFICULTY_WEIGHT = {1: 0.6, 2: 0.8, 3: 1.0}


class KnowledgeStatus(StrEnum):
    MASTERED = "mastered"  # ✅ maîtrisée
    TO_REVIEW = "to_review"  # 🟠 à revoir
    NOT_MASTERED = "not_mastered"  # 🔴 non maîtrisée


@dataclass(frozen=True)
class Evidence:
    """Preuve de maîtrise d'une notion apportée par une tentative (table attempt_evidence)."""

    knowledge_id: str
    result: float  # 0 à 1
    weight: float  # §9.3
    activity_type: ActivityCode
    replay: bool = False  # tentative du bloc « reprise des erreurs »


def evidence_weight(activity_type: ActivityCode, difficulty: int, registry: ActivityRegistry) -> float:
    return DIFFICULTY_WEIGHT[difficulty] * registry.get(activity_type).evidence_factor


def evidences_from(
    activity: BuiltActivity, grade: Grade, registry: ActivityRegistry, replay: bool = False
) -> list[Evidence]:
    weight = evidence_weight(activity.type, activity.difficulty, registry)
    return [
        Evidence(knowledge_id, result, weight, activity.type, replay)
        for knowledge_id, result in grade.evidence.items()
    ]


def session_rates(evidences: Sequence[Evidence]) -> dict[str, float]:
    """taux_séance(notion) = Σ(poids × résultat) / Σ(poids), reprise comprise (§9.3)."""
    totals: dict[str, list[float]] = {}
    for e in evidences:
        weighted, weights = totals.setdefault(e.knowledge_id, [0.0, 0.0])
        totals[e.knowledge_id] = [weighted + e.weight * e.result, weights + e.weight]
    return {k: weighted / weights for k, (weighted, weights) in totals.items()}


def status(rate: float) -> KnowledgeStatus:
    if rate >= MASTERED_RATE:
        return KnowledgeStatus.MASTERED
    if rate >= FRAGILE_RATE:
        return KnowledgeStatus.TO_REVIEW
    return KnowledgeStatus.NOT_MASTERED


def score_on_10(main_scores: Sequence[float]) -> float:
    """Note de la séance : moyenne des activités principales, sur 10, arrondie à 0,5 (§9.2)."""
    if not main_scores:
        return 0.0
    return math.floor(10 * sum(main_scores) / len(main_scores) * 2 + 0.5) / 2


@dataclass(frozen=True)
class KnowledgeResult:
    knowledge_id: str
    session_rate: float
    status: KnowledgeStatus
    mastery: Mastery  # après la séance


@dataclass(frozen=True)
class SessionOutcome:
    score_on_10: float
    results: list[KnowledgeResult]  # de la plus fragile à la plus solide
    next_review_at: datetime | None  # prochaine révision de la leçon
    lesson_mastered: bool

    def count(self, status: KnowledgeStatus) -> int:
        return sum(1 for r in self.results if r.status is status)

    @property
    def can_review_errors(self) -> bool:
        return any(r.status is not KnowledgeStatus.MASTERED for r in self.results)

    @property
    def errors(self) -> list[str]:
        return [r.knowledge_id for r in self.results if r.status is not KnowledgeStatus.MASTERED]


def summarize_session(
    main_scores: Sequence[float],
    evidences: Sequence[Evidence],
    masteries: Mapping[str, Mastery],
    importance: Mapping[str, int],
    now: datetime,
) -> SessionOutcome:
    """Bilan de fin de séance (écran 7) et nouvelles maîtrises à enregistrer.

    `masteries` : maîtrises de toutes les notions de la leçon avant la séance.
    `importance` : importance de toutes les notions de la leçon.
    """
    results = []
    for knowledge_id, rate in session_rates(evidences).items():
        mastery = update_mastery(masteries.get(knowledge_id), rate, now)
        results.append(KnowledgeResult(knowledge_id, rate, status(rate), mastery))
    results.sort(key=lambda r: (r.session_rate, -importance.get(r.knowledge_id, 0), r.knowledge_id))

    after = {**masteries, **{r.knowledge_id: r.mastery for r in results}}
    review = lesson_review((imp, after.get(k)) for k, imp in importance.items())
    return SessionOutcome(
        score_on_10=score_on_10(main_scores),
        results=results,
        next_review_at=review.next_review_at,
        lesson_mastered=review.mastered,
    )
