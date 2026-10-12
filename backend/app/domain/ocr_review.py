"""Relecture d'une photo par l'enfant : « Peux-tu vérifier ? » (cahier des charges complet §10 ;
spécification technique §6.3).

L'OCR signale les passages importants qu'il a mal lus (un nom, une date, un mot-clé) avec les
mots qui les entourent. Plutôt que d'analyser une leçon peut-être fausse, on demande à l'enfant,
qui a le cahier sous les yeux, de confirmer ou de corriger ; puis on corrige le texte lu.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

MAX_REVIEW_ITEMS = 5
MAX_SPAN_LENGTH = 80
MAX_ANSWER_LENGTH = 120
UNREADABLE = "[illisible]"


@dataclass(frozen=True)
class Uncertain:
    """Un passage douteux : ce que l'OCR a lu, et le bout de phrase exact qui le contient."""

    page_index: int
    text: str
    context: str


class ReviewStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"  # c'est bien ce qui est écrit
    CORRECTED = "corrected"  # l'enfant a écrit le bon mot
    UNKNOWN = "unknown"  # l'enfant ne sait pas non plus : on garde la lecture


def select_uncertain(pages: Iterable[tuple[int, str, Sequence[tuple[str, str]]]]) -> list[Uncertain]:
    """Passages signalés et vérifiables : le passage est dans son contexte, le contexte est dans
    le texte de la page (recopié exactement), pas de doublon ; 5 au plus, dans l'ordre des pages.

    `pages` : (index, texte lu, [(passage, contexte)…]).
    """
    selected: list[Uncertain] = []
    seen: set[tuple[int, str]] = set()
    for index, page_text, spans in sorted(pages, key=lambda p: p[0]):
        for raw_text, raw_context in spans:
            text, context = raw_text.strip(), raw_context.strip()
            if not text or len(text) > MAX_SPAN_LENGTH or text not in context or context not in page_text:
                continue
            if (index, context) in seen:
                continue
            seen.add((index, context))
            selected.append(Uncertain(index, text, context))
    return selected[:MAX_REVIEW_ITEMS]


@dataclass(frozen=True)
class Answer:
    page_index: int
    read_text: str
    context: str
    status: ReviewStatus
    correction: str | None = None


def apply_answers(page_index: int, page_text: str, answers: Iterable[Answer]) -> str:
    """Texte de la page, corrigé par les réponses de l'enfant (seulement les corrections)."""
    for answer in answers:
        if answer.page_index != page_index or answer.status is not ReviewStatus.CORRECTED:
            continue
        correction = (answer.correction or "").strip()
        if not correction or answer.context not in page_text:
            continue
        fixed_context = answer.context.replace(answer.read_text, correction, 1)
        page_text = page_text.replace(answer.context, fixed_context, 1)
    return page_text
