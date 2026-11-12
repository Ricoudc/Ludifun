"""Niveau de confiance de chaque notion extraite d'une leçon (cahier des charges §115).

Calculé par le code, sans IA, à partir de ce qui peut faire douter de la notion :

- la page où se trouve le passage cité a été mal lue (qualité « partielle » ou « illisible ») ;
- le passage cité n'est retrouvé qu'approximativement dans le texte lu (lecture imparfaite) ;
- un mot illisible est dans le passage ou dans la notion ;
- un nombre de la notion (une date, une quantité) n'est nulle part dans la leçon.

Le niveau décide du comportement : confiance élevée, la notion est utilisée ; moyenne, elle est
utilisée et le parent est invité à la vérifier ; faible, elle n'est pas proposée à l'enfant tant
que le parent ne l'a pas confirmée (« ne pas inventer »).
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.domain.knowledge import KnowledgeItem
from app.domain.ocr_review import UNREADABLE
from app.domain.rules import RULES
from app.domain.text import fuzzy_contains, normalize

HIGH = RULES.confidence.high
LOW = RULES.confidence.low
PAGE_FACTORS = {"good": 1.0, "partial": 0.7, "unreadable": 0.3}
APPROXIMATE_FACTOR = 0.8  # passage retrouvé avec des différences
MISSING_FACTOR = 0.5  # passage introuvable
UNREADABLE_FACTOR = 0.5
UNKNOWN_NUMBER_FACTOR = 0.6
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


class Trust(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class Confidence:
    value: float  # 0 à 1
    reasons: tuple[str, ...]  # ce qui fait douter, en français, pour le parent

    @property
    def trust(self) -> Trust:
        if self.value >= HIGH:
            return Trust.HIGH
        return Trust.MEDIUM if self.value >= LOW else Trust.LOW


def _numbers(text: str) -> set[str]:
    return {n.replace(",", ".") for n in _NUMBER.findall(text)}


def notion_confidence(item: KnowledgeItem, pages: Sequence[tuple[str, str]]) -> Confidence:
    """`pages` : (qualité de lecture, texte lu) de chaque page de la leçon."""
    value, reasons = 1.0, []
    excerpt = normalize(item.source_excerpt)
    exact = [quality for quality, text in pages if excerpt and excerpt in normalize(text)]
    approximate = [quality for quality, text in pages if fuzzy_contains(text, item.source_excerpt)]
    if exact or approximate:
        quality = (exact or approximate)[0]
        if not exact:
            value *= APPROXIMATE_FACTOR
            reasons.append("le passage de la leçon n'a été retrouvé qu'avec des différences")
        if PAGE_FACTORS.get(quality, 1.0) < 1.0:
            value *= PAGE_FACTORS[quality]
            reasons.append(
                "la page a été mal lue" if quality == "unreadable" else "la page a été lue en partie"
            )
    else:
        value *= MISSING_FACTOR
        reasons.append("le passage cité n'a pas été retrouvé dans la leçon")
    if any(UNREADABLE in text for text in (item.source_excerpt, item.statement, item.label)):
        value *= UNREADABLE_FACTOR
        reasons.append("un mot du passage était illisible")
    lesson_numbers = set().union(*(_numbers(text) for _, text in pages)) if pages else set()
    unknown = sorted(_numbers(f"{item.label} {item.statement}") - lesson_numbers)
    if unknown:
        value *= UNKNOWN_NUMBER_FACTOR
        reasons.append(f"« {unknown[0]} » n'est écrit nulle part dans la leçon")
    return Confidence(round(value, 2), tuple(reasons))
