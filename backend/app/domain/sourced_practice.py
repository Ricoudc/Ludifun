"""Exercices tirés des sites de confiance (étape 29, cahier des charges complet §116-117).

Une fois la leçon prête, si le parent l'a permis, Ludifun cherche des pages sur des sites
éducatifs autorisés (Vikidia, Lumni, Éduscol…) pour les notions les plus importantes, et l'IA
en tire des questions à choix : d'autres exemples que ceux de la leçon, pour s'entraîner. Le code
ne garde une question que si :

- elle passe les contrôles des questions de la leçon (réponse absente de l'énoncé, trois
  distracteurs distincts de même nature, rien qui renvoie à une fiche ou une image absente) ;
- sa citation figure vraiment dans l'extrait cité, et contient la bonne réponse : la réponse
  vient de la page, pas de la mémoire de l'IA ;
- elle parle de la notion de la leçon (un mot important en commun) ;
- elle n'est pas déjà dans la leçon (`app.domain.duplicates`, vérifié par l'appelant).

Une question gardée porte sa source (site, page, phrase) : l'enfant voit « D'après … », la
correction cite la phrase, le parent la voit dans les questions de la leçon.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from app.domain.child_safety import unsafe_reason
from app.domain.knowledge import KnowledgeItem, MaterialQuestion, QuestionSource
from app.domain.rules import RULES
from app.domain.sources import MIN_QUOTE, Excerpt, keywords
from app.domain.text import contains_words, fuzzy_contains
from app.domain.validation import (
    PICTURE_REASON,
    SUPPORT_REASON,
    Rejection,
    check_question,
    needs_picture,
    needs_support,
)

NOTIONS = RULES.material.sourced_notions  # notions les plus importantes, par leçon
PER_NOTION = RULES.material.sourced_per_notion  # questions gardées au plus par notion


@dataclass(frozen=True)
class ProposedQuestion:
    """Ce que l'IA propose : une question à choix et la phrase de l'extrait qui la prouve."""

    stem: str
    answer: str
    distractors: list[str]
    difficulty: int
    source: int  # numéro de l'extrait
    quote: str


@dataclass(frozen=True)
class CheckedPractice:
    questions: list[MaterialQuestion] = field(default_factory=list)
    rejected: list[Rejection] = field(default_factory=list)


def check_practice(
    item: KnowledgeItem,
    proposed: Sequence[ProposedQuestion],
    excerpts: Sequence[Excerpt],
    limit: int = PER_NOTION,
) -> CheckedPractice:
    """Les questions proposées pour la notion `item`, contrôlées une à une."""
    by_number = {e.number: e for e in excerpts}
    topic = keywords(f"{item.label} {item.statement}")
    kept: list[MaterialQuestion] = []
    rejected: list[Rejection] = []
    for i, p in enumerate(proposed):
        label = f"sources[{i}]"
        quote = " ".join(p.quote.split())
        excerpt = by_number.get(p.source)
        question, reason = check_question(
            {
                "difficulty": min(max(p.difficulty, 1), 2),
                "stem": p.stem,
                "answer": p.answer,
                "distractors": p.distractors,
            }
        )
        if question is not None:
            if needs_picture(question.stem):
                reason = PICTURE_REASON
            elif needs_support(question.stem):
                reason = SUPPORT_REASON
            elif excerpt is None or len(quote) < MIN_QUOTE or not fuzzy_contains(excerpt.text, quote):
                reason = "citation absente de l'extrait cité"
            elif not (contains_words(quote, question.answer) or fuzzy_contains(quote, question.answer)):
                reason = "la citation ne contient pas la bonne réponse"
            elif not topic & keywords(f"{question.stem} {question.answer} {quote}"):
                reason = "la question ne parle pas de la notion de la leçon"
            elif unsafe := unsafe_reason(
                [question.stem, question.answer, *question.distractors], [excerpt.text, item.corpus()]
            ):
                reason = unsafe
            elif len(kept) >= limit:
                reason = f"plus de {limit} questions pour cette notion"
        if question is None or reason:
            rejected.append(Rejection(label, reason))
            continue
        assert excerpt is not None
        kept.append(
            question.model_copy(
                update={"source": QuestionSource(site=excerpt.site, url=excerpt.url, quote=quote)}
            )
        )
    return CheckedPractice(kept, rejected)
