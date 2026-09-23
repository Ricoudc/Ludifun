"""Validateurs automatiques des sorties de l'IA (cahier des charges §6.4).

Principe : on écarte l'élément fautif, pas la leçon entière. Chaque rejet est
tracé (`Rejection`) pour mesurer la qualité de l'IA pendant les tests.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.domain.knowledge import (
    Cloze,
    Flashcard,
    KnowledgeItem,
    KnowledgeMaterial,
    LessonAnalysis,
    LessonInfo,
    MaterialQuestion,
    Pair,
)
from app.domain.text import compatible_natures, contains_words, fuzzy_contains, normalize

TIP_MAX_LENGTH = 120
BLANK = "___"


class AnalysisError(ValueError):
    """La sortie de l'analyse est inexploitable dans son ensemble (pas seulement une notion)."""


@dataclass(frozen=True)
class Rejection:
    element: str  # "k3", "questions[1]", "cloze"…
    reason: str


@dataclass(frozen=True)
class AnalysisValidation:
    analysis: LessonAnalysis
    rejected: list[Rejection] = field(default_factory=list)


@dataclass(frozen=True)
class MaterialValidation:
    material: KnowledgeMaterial
    rejected: list[Rejection] = field(default_factory=list)

    @property
    def rejection_rate(self) -> float:
        kept = (
            len(self.material.questions)
            + len(self.material.true_statements)
            + len(self.material.false_statements)
            + sum(x is not None for x in (self.material.cloze, self.material.pair, self.material.flashcard))
            + (self.material.tip is not None)
        )
        total = kept + len(self.rejected)
        return len(self.rejected) / total if total else 0.0


def _first_error(exc: ValidationError) -> str:
    error = exc.errors()[0]
    location = ".".join(str(part) for part in error["loc"])
    return f"{location}: {error['msg']}" if location else error["msg"]


# --------------------------------------------------------------------------- #
# Analyse de la leçon
# --------------------------------------------------------------------------- #


def validate_analysis(raw: Mapping[str, Any], ocr_text: str) -> AnalysisValidation:
    if not isinstance(raw.get("is_lesson"), bool):
        raise AnalysisError("is_lesson manquant")
    if not raw["is_lesson"]:
        return AnalysisValidation(LessonAnalysis(is_lesson=False, lesson=None, knowledge=[]))
    try:
        lesson = LessonInfo.model_validate(raw.get("lesson"))
    except ValidationError as exc:
        raise AnalysisError(f"leçon invalide ({_first_error(exc)})") from exc

    rejected: list[Rejection] = []
    items: list[KnowledgeItem] = []
    raw_items = raw.get("knowledge")
    for index, raw_item in enumerate(raw_items if isinstance(raw_items, list) else []):
        name = raw_item.get("id") if isinstance(raw_item, dict) else None
        element = str(name) if name else f"knowledge[{index}]"
        try:
            item = KnowledgeItem.model_validate(raw_item)
        except ValidationError as exc:
            rejected.append(Rejection(element, _first_error(exc)))
            continue
        if any(existing.id == item.id for existing in items):
            rejected.append(Rejection(element, "identifiant en double"))
        elif not fuzzy_contains(ocr_text, item.source_excerpt):
            rejected.append(Rejection(element, "source_excerpt introuvable dans le texte de la leçon"))
        else:
            items.append(item)

    # Une relation vers une notion absente (ou rejetée) est retirée, la notion est gardée.
    known = {item.id for item in items}
    warnings = [w for w in raw.get("warnings", []) if isinstance(w, str)]
    cleaned: list[KnowledgeItem] = []
    for item in items:
        relations = [r for r in item.relations if r.target in known and r.target != item.id]
        if len(relations) != len(item.relations):
            warnings.append(f"{item.id} : relation vers une notion inconnue retirée")
        cleaned.append(item.model_copy(update={"relations": relations}))

    analysis = LessonAnalysis(
        schema_version=str(raw.get("schema_version", "1.0")),
        is_lesson=True,
        lesson=lesson,
        knowledge=cleaned,
        warnings=warnings,
    )
    return AnalysisValidation(analysis, rejected)


# --------------------------------------------------------------------------- #
# Matériel par notion
# --------------------------------------------------------------------------- #

_NEGATION_WORDS = {"ne", "n", "pas", "jamais", "plus"}
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ][\wÀ-ÖØ-öø-ÿ'-]*")
_SENTENCE_START = re.compile(r"(^|[.!?:]\s+)$")


def _without_negation(sentence: str) -> str:
    return " ".join(w for w in normalize(sentence).split() if w not in _NEGATION_WORDS)


def _check_question(raw: Any) -> tuple[MaterialQuestion | None, str]:
    if not isinstance(raw, dict):
        return None, "format invalide"
    answer = str(raw.get("answer", "")).strip()
    stem = str(raw.get("stem", "")).strip()
    raw_distractors = raw.get("distractors")
    distractors: list[str] = []
    seen = {normalize(answer)}
    for d in raw_distractors if isinstance(raw_distractors, list) else []:
        text = str(d).strip()
        if text and normalize(text) not in seen and compatible_natures(answer, text):
            seen.add(normalize(text))
            distractors.append(text)
    if answer and stem and contains_words(stem, answer):
        return None, "l'énoncé contient la réponse"
    if len(distractors) < 3:
        return None, "moins de 3 distracteurs valides (distincts, différents de la réponse, de même nature)"
    try:
        return MaterialQuestion.model_validate({**raw, "distractors": distractors[:3]}), ""
    except ValidationError as exc:
        return None, _first_error(exc)


def _check_cloze(raw: Any) -> tuple[Cloze | None, str]:
    try:
        cloze = Cloze.model_validate(raw)
    except ValidationError as exc:
        return None, _first_error(exc)
    if cloze.text.count(BLANK) != 1:
        return None, "la phrase doit contenir exactement un « ___ »"
    rest = cloze.text.replace(BLANK, " ")
    if any(contains_words(rest, answer) for answer in cloze.answers):
        return None, "la réponse apparaît ailleurs dans la phrase"
    return cloze, ""


def _check_tip(tip: str, item: KnowledgeItem) -> str:
    if len(tip) > TIP_MAX_LENGTH:
        return f"astuce trop longue (> {TIP_MAX_LENGTH} caractères)"
    corpus = item.corpus()
    corpus_numbers = {n.replace(",", ".") for n in _NUMBER.findall(corpus)}
    for number in _NUMBER.findall(tip):
        if number.replace(",", ".") not in corpus_numbers:
            return f"l'astuce contient un nombre absent de la notion ({number})"
    corpus_words = set(normalize(corpus).split())
    for match in _WORD.finditer(tip):
        word = match.group()
        at_sentence_start = _SENTENCE_START.search(tip[: match.start()]) is not None
        if word[0].isupper() and not at_sentence_start and not set(normalize(word).split()) <= corpus_words:
            return f"l'astuce contient un nom propre absent de la notion ({word})"
    return ""


def validate_material(item: KnowledgeItem, raw: Mapping[str, Any]) -> MaterialValidation:
    rejected: list[Rejection] = []

    questions: list[MaterialQuestion] = []
    raw_questions = raw.get("questions")
    for i, raw_question in enumerate(raw_questions if isinstance(raw_questions, list) else []):
        question, reason = _check_question(raw_question)
        if question is None:
            rejected.append(Rejection(f"questions[{i}]", reason))
        else:
            questions.append(question)

    true_statements: list[str] = []
    raw_true = raw.get("true_statements")
    for i, s in enumerate(raw_true if isinstance(raw_true, list) else []):
        text = str(s).strip()
        if not text or normalize(text) in {normalize(t) for t in true_statements}:
            rejected.append(Rejection(f"true_statements[{i}]", "vide ou en double"))
        else:
            true_statements.append(text)

    truths = [item.statement, *true_statements]
    false_statements: list[str] = []
    raw_false = raw.get("false_statements")
    for i, s in enumerate(raw_false if isinstance(raw_false, list) else []):
        text = str(s).strip()
        if not text or normalize(text) in {normalize(f) for f in false_statements}:
            rejected.append(Rejection(f"false_statements[{i}]", "vide ou en double"))
        elif any(normalize(text) == normalize(t) for t in truths):
            rejected.append(Rejection(f"false_statements[{i}]", "identique à une affirmation vraie"))
        elif any(_without_negation(text) == _without_negation(t) for t in truths):
            rejected.append(Rejection(f"false_statements[{i}]", "simple négation d'une affirmation vraie"))
        else:
            false_statements.append(text)

    cloze: Cloze | None = None
    if raw.get("cloze") is not None:
        cloze, reason = _check_cloze(raw["cloze"])
        if cloze is None:
            rejected.append(Rejection("cloze", reason))

    pair: Pair | None = None
    if raw.get("pair") is not None:
        try:
            pair = Pair.model_validate(raw["pair"])
        except ValidationError as exc:
            rejected.append(Rejection("pair", _first_error(exc)))

    flashcard: Flashcard | None = None
    if raw.get("flashcard") is not None:
        try:
            flashcard = Flashcard.model_validate(raw["flashcard"])
            if normalize(flashcard.front) == normalize(flashcard.back):
                flashcard = None
                rejected.append(Rejection("flashcard", "recto et verso identiques"))
        except ValidationError as exc:
            rejected.append(Rejection("flashcard", _first_error(exc)))

    tip: str | None = None
    if isinstance(raw.get("tip"), str) and raw["tip"].strip():
        reason = _check_tip(raw["tip"].strip(), item)
        if reason:
            rejected.append(Rejection("tip", reason))
        else:
            tip = raw["tip"].strip()

    explanation = raw.get("explanation")
    if not isinstance(explanation, str) or not explanation.strip():
        rejected.append(Rejection("explanation", "absente : la phrase « à retenir » est utilisée"))
        explanation = item.statement

    material = KnowledgeMaterial(
        knowledge_id=item.id,
        questions=questions,
        true_statements=true_statements,
        false_statements=false_statements,
        cloze=cloze,
        pair=pair,
        flashcard=flashcard,
        tip=tip,
        explanation=explanation.strip(),
    )
    return MaterialValidation(material, rejected)
