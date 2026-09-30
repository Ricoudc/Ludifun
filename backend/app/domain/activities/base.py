"""Contrat commun des activités (cahier des charges §7).

Une activité se construit à partir d'une ou plusieurs `KnowledgeUnit` (notion + matériel)
et produit :
- un `payload` public, envoyé au téléphone ;
- une `solution` privée, qui contient aussi le retour à afficher après la réponse,
  pour que la correction n'ait besoin de rien d'autre.
"""

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from app.domain.errors import ErrorType
from app.domain.knowledge import KnowledgeType, KnowledgeUnit


class ActivityCode(StrEnum):
    MCQ = "MCQ"
    TRUE_FALSE = "TRUE_FALSE"
    FILL_BLANK = "FILL_BLANK"
    MATCH = "MATCH"
    SPEED_CHALLENGE = "SPEED_CHALLENGE"
    FLASHCARD = "FLASHCARD"
    OPEN_QUESTION = "OPEN_QUESTION"
    # Activités graphiques (étape 21).
    ORDER = "ORDER"  # remettre les étapes dans l'ordre
    TIMELINE = "TIMELINE"  # frise chronologique
    CLASSIFY = "CLASSIFY"  # ranger dans les bonnes cases
    MEMORY = "MEMORY"  # retrouver les paires
    # Activités sur une figure (étape 22).
    MAP = "MAP"  # situer sur une carte ou un schéma
    COLORING = "COLORING"  # colorier selon une légende
    # Jeux d'orthographe : apprendre à écrire les mots d'une liste.
    WORD_FLASH = "WORD_FLASH"  # mot éclair : voir le mot, puis l'écrire de mémoire
    SCRAMBLE = "SCRAMBLE"  # lettres mélangées à remettre dans l'ordre


Result = Literal["correct", "partial", "incorrect"]


class InvalidResponse(ValueError):
    """La réponse envoyée par le téléphone ne respecte pas le format de l'activité."""


class CannotBuild(ValueError):
    """Le matériel disponible ne permet pas de construire cette activité."""


@dataclass(frozen=True)
class BuiltActivity:
    type: ActivityCode
    difficulty: int
    knowledge_ids: list[str]
    payload: dict[str, Any]
    solution: dict[str, Any]


@dataclass(frozen=True)
class Grade:
    score: float  # 0 à 1
    evidence: dict[str, float]  # résultat par notion couverte (0 à 1), pour la maîtrise
    correct_answer: str  # la bonne réponse, lisible par l'enfant
    tip: str | None = None
    explanation: str | None = None
    details: list[dict[str, Any]] = field(default_factory=list)  # élément par élément (MATCH, SPEED)
    errors: dict[str, ErrorType] = field(default_factory=dict)  # type d'erreur par notion ratée

    @property
    def result(self) -> Result:
        if self.score >= 1:
            return "correct"
        if self.score >= 0.5:
            return "partial"
        return "incorrect"


class ResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def parse_response[R: ResponseModel](model: type[R], response: dict[str, Any]) -> R:
    try:
        return model.model_validate(response)
    except ValidationError as exc:
        raise InvalidResponse(str(exc.errors()[0]["msg"])) from exc


def feedback(unit: KnowledgeUnit) -> dict[str, Any]:
    """Astuce et explication stockées dans la solution, affichées après la réponse."""
    return {"tip": unit.material.tip, "explanation": unit.material.explanation}


class ActivityType(ABC):
    code: ClassVar[ActivityCode]
    knowledge_types: ClassVar[frozenset[KnowledgeType]]
    difficulties: ClassVar[frozenset[int]]
    base_duration_s: ClassVar[int]  # estimation de durée (§8.2)
    # Poids de la preuve de maîtrise (§9.3) : 0,5 quand la réponse peut être due
    # au hasard (vrai/faux) ou est une auto-évaluation (carte mémoire).
    evidence_factor: ClassVar[float] = 1.0
    multi_knowledge: ClassVar[bool] = False
    min_units: ClassVar[int] = 1
    max_units: ClassVar[int] = 1

    def accepts(self, unit: KnowledgeUnit) -> bool:
        """La notion est d'un type compatible (§7.2) et a le matériel nécessaire."""
        return unit.type in self.knowledge_types and self._has_material(unit)

    def can_build(self, units: list[KnowledgeUnit], difficulty: int) -> bool:
        return (
            difficulty in self.difficulties
            and self.min_units <= len(units) <= self.max_units
            and all(self.accepts(u) for u in units)
            and self._can_combine(units, difficulty)
        )

    def combinable(self, units: list[KnowledgeUnit], difficulty: int) -> bool:
        """Ces notions peuvent aller ensemble (activités à plusieurs notions), quel que soit leur nombre."""
        return all(self.accepts(u) for u in units) and self._can_combine(units, difficulty)

    def build(self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random) -> BuiltActivity:
        if not self.can_build(units, difficulty):
            raise CannotBuild(
                f"{self.code} impossible avec {[u.id for u in units]} (difficulté {difficulty})"
            )
        payload, solution = self._build(units, difficulty, rng)
        return BuiltActivity(self.code, difficulty, [u.id for u in units], payload, solution)

    def grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade:
        if activity.type != self.code:
            raise ValueError(f"activité {activity.type} corrigée par {self.code}")
        return self._grade(activity, response)

    @abstractmethod
    def _has_material(self, unit: KnowledgeUnit) -> bool: ...

    def _can_combine(self, units: list[KnowledgeUnit], difficulty: int) -> bool:
        return True

    @abstractmethod
    def _build(
        self, units: list[KnowledgeUnit], difficulty: int, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]: ...

    @abstractmethod
    def _grade(self, activity: BuiltActivity, response: dict[str, Any]) -> Grade: ...


ALL_TYPES = frozenset(KnowledgeType)
