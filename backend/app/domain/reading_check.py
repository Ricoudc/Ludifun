"""Vérifier une date lue sur la photo avec des sources (étape 24c) : ce que le code décide.

Une photo de cahier se lit parfois mal : « 1798 » au lieu de « 1789 ». Si l'année lue n'apparaît
dans aucune source, alors qu'au moins deux sources donnent une année qui n'en diffère que d'un
chiffre (inversé ou changé), on demande à l'enfant de vérifier (« Peux-tu vérifier ? »), sans lui
souffler la réponse. Pas d'IA ici : des années et une distance entre chiffres. Prudent : au moindre
doute sur les sources (année lue présente, pas assez de sources d'accord), on ne demande rien.
"""

import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.domain.ocr_review import Uncertain, select_uncertain
from app.domain.text import damerau_levenshtein

# Une année entière : pas collée à d'autres chiffres, ni après une virgule décimale (« 3,1789 »).
_YEAR = re.compile(r"(?<![\d,.])(1\d{3}|20\d{2})(?!\d)")
MIN_SOURCES = 2  # sources qui doivent donner la même autre année
CONTEXT = 40  # signes gardés de chaque côté de l'année, pour la montrer à l'enfant


@dataclass(frozen=True)
class YearDoubt:
    read: str  # l'année lue sur la photo
    expected: str  # l'année des sources (jamais montrée à l'enfant)


def years(text: str) -> set[str]:
    return set(_YEAR.findall(text))


def doubtful_years(read: Iterable[str], sources: Sequence[str]) -> list[YearDoubt]:
    """Années lues absentes de toutes les sources, alors qu'au moins deux sources donnent une
    année à un chiffre près (1798 → 1789, 1879 → 1789)."""
    in_sources = [years(text) for text in sources]
    doubts = []
    for year in sorted(set(read)):
        if any(year in found for found in in_sources):
            continue
        close = Counter(
            other for found in in_sources for other in found if damerau_levenshtein(other, year) == 1
        )
        if close:
            expected, count = close.most_common(1)[0]
            if count >= MIN_SOURCES:
                doubts.append(YearDoubt(year, expected))
    return doubts


def review_items(doubts: Sequence[YearDoubt], pages: Sequence[tuple[int, str]]) -> list[Uncertain]:
    """Passages à faire vérifier : chaque année douteuse dans la phrase de la page où elle a été
    lue (le premier endroit), au format de « Peux-tu vérifier ? »."""
    spans: dict[int, list[tuple[str, str]]] = {}
    for doubt in doubts:
        for index, text in pages:
            match = re.search(rf"(?<![\d,.]){doubt.read}(?!\d)", text)
            if match is None:
                continue
            start, end = max(0, match.start() - CONTEXT), min(len(text), match.end() + CONTEXT)
            # Couper aux espaces pour ne pas montrer de mots tronqués.
            while start > 0 and not text[start - 1].isspace():
                start += 1
            while end < len(text) and not text[end].isspace():
                end -= 1
            context = text[start:end].strip() if end > start else doubt.read
            if doubt.read not in context:
                context = text[match.start() : match.end()]
            spans.setdefault(index, []).append((doubt.read, context))
            break
    return select_uncertain((index, text, spans.get(index, [])) for index, text in pages)
