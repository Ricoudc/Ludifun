"""Correction des réponses (IA 4 pour les réponses libres, règles pour le reste)."""

import json
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from app.ai.client import LLM
from app.models import Question

# Au-delà de ce seuil de similarité, une faute de frappe est tolérée (texte à trous).
TYPO_TOLERANCE = 0.85
PASS_SCORE = 0.6


@dataclass
class Evaluation:
    score: float
    correct: bool
    feedback: str
    expected: str
    missing_points: list[str] = field(default_factory=list)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.strip().lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.replace("’", "'").split()).strip(" .!?")


def _close_enough(given: str, expected: str) -> bool:
    a, b = normalize(given), normalize(expected)
    return a == b or (bool(a) and SequenceMatcher(None, a, b).ratio() >= TYPO_TOLERANCE)


def _grade_association(question: Question, given: str) -> float:
    """`given` est un objet JSON {gauche: droite}."""
    try:
        mapping = json.loads(given)
    except (json.JSONDecodeError, TypeError):
        return 0.0
    if not isinstance(mapping, dict) or not question.pairs:
        return 0.0
    expected = {normalize(p["left"]): normalize(p["right"]) for p in question.pairs}
    good = sum(1 for k, v in mapping.items() if expected.get(normalize(str(k))) == normalize(str(v)))
    return good / len(expected)


def evaluate(question: Question, given: str, llm: LLM, grade: str) -> Evaluation:
    kind = question.kind
    if kind in ("qcm", "vrai_faux"):
        score = 1.0 if normalize(given) == normalize(question.answer) else 0.0
    elif kind == "texte_a_trous":
        score = 1.0 if _close_enough(given, question.answer) else 0.0
    elif kind == "flashcard":
        # Auto-évaluation : l'enfant retourne la carte puis indique s'il savait.
        score = 1.0 if normalize(given) in ("je savais", "oui", "1", "true") else 0.0
    elif kind == "association":
        score = _grade_association(question, given)
    elif kind == "question_ouverte":
        result = llm.evaluate_open_answer(question.prompt, question.answer, given, grade)
        score = max(0.0, min(1.0, result.score))
        return Evaluation(
            score=score,
            correct=score >= PASS_SCORE,
            feedback=result.feedback,
            expected=question.answer,
            missing_points=result.missing_points,
        )
    else:
        raise ValueError(f"Type de question inconnu : {kind}")

    correct = score >= PASS_SCORE
    feedback = "Bravo ! " + question.explanation if correct else "Pas tout à fait. " + question.explanation
    return Evaluation(score=score, correct=correct, feedback=feedback, expected=question.answer)
