"""Une question garde son contexte : elle donne ce dont elle parle (le mot, la phrase, le
nombre), sinon l'enfant ne peut pas répondre."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.domain.validation import CONTEXT_REASON, lacks_context, validate_analysis, validate_material

REFERENCE = sorted((Path(__file__).resolve().parents[2] / "reference_lessons").glob("*.json"))


@pytest.mark.parametrize(
    "text",
    [
        "Quel est le pluriel de ce mot ?",
        "Cette phrase est-elle au présent ?",
        "Quel est le double de ce nombre ?",
        "Conjugue le verbe souligné au présent.",
        "Quel est le mot en gras ?",
        "Complète la phrase suivante.",
        "Quelle est la nature du mot entouré ?",
        "Le nom « trésor » est-il masculin ? Regarde le mot souligné.",
    ],
)
def test_a_question_without_what_it_talks_about_is_recognized(text: str) -> None:
    assert lacks_context(text)


@pytest.mark.parametrize(
    "text",
    [
        "Quel est le pluriel du mot « cheval » ?",
        "Quel est le pluriel de ce mot : cheval ?",
        "La phrase « Le chat dort. » est-elle au présent ?",
        "Complète la phrase suivante : Le chat ___ sur le lit.",
        "Lequel de ces mots est un verbe ?",
        "Parmi les mots suivants, lequel est un nom ?",
        "Un carré a 4 côtés égaux. Combien d'angles droits a cette figure ?",
        "Le chien ___ dans le jardin.",
        "Quel article va avec « maisons » ?",
        "En quelle année commence la Révolution française ?",
    ],
)
def test_a_question_that_gives_its_data_is_kept(text: str) -> None:
    assert not lacks_context(text)


def _texts(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [t for v in value.values() for t in _texts(v)]
    return [t for v in value for t in _texts(v)] if isinstance(value, list) else []


def test_no_question_of_the_reference_lessons_is_rejected_for_its_context() -> None:
    for path in REFERENCE:
        raw = json.loads(path.read_text(encoding="utf-8"))
        analysis = validate_analysis(raw["analysis"], raw["ocr_text"]).analysis
        for item in analysis.knowledge:
            checked = validate_material(item, raw["material"][item.id], raw["ocr_text"])
            assert [r for r in checked.rejected if r.reason == CONTEXT_REASON] == [], path.name


def test_a_question_without_its_context_is_rejected_and_the_rest_is_kept() -> None:
    raw = json.loads(REFERENCE[0].read_text(encoding="utf-8"))
    item = validate_analysis(raw["analysis"], raw["ocr_text"]).analysis.knowledge[0]
    material = json.loads(json.dumps(raw["material"][item.id]))
    before = validate_material(item, material, raw["ocr_text"])
    assert len(before.material.questions) >= 2
    kept_stem = material["questions"][1]["stem"]
    material["questions"][0]["stem"] = "Quel est le pluriel de ce mot ?"

    checked = validate_material(item, material, raw["ocr_text"])
    assert any(r.element == "questions[0]" and r.reason == CONTEXT_REASON for r in checked.rejected)
    assert len(checked.material.questions) == len(before.material.questions) - 1
    assert kept_stem in [q.stem for q in checked.material.questions]
    assert "mets le mot" in CONTEXT_REASON  # la raison dit à l'IA quoi faire au nouvel essai
