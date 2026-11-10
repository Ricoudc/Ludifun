"""Un texte écrit en anglais par l'IA n'arrive pas devant l'enfant, hors leçon d'anglais."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.domain.knowledge import Subject
from app.domain.text import written_in_english
from app.domain.validation import ENGLISH_REASON, validate_analysis, validate_material

REFERENCE = sorted((Path(__file__).resolve().parents[2] / "reference_lessons").glob("*.json"))
SEEN = "The correct word to complete the noun 'trésor' is 'un'."  # téléphone d'essai, leçon de français


@pytest.mark.parametrize(
    "text",
    [SEEN, "Which word is the subject of the sentence?", "This is not the answer.", "What does the verb do?"],
)
def test_english_sentences_are_recognized(text: str) -> None:
    assert written_in_english(text)


@pytest.mark.parametrize(
    "text",
    [
        "Le nom « trésor » prend le déterminant « un ».",
        "Tolkien a écrit « The Lord of the Rings » en 1954.",
        "Le mot 'the' se traduit par le, la ou les.",
        "On dit week-end, football et sandwich.",
        "Le do est la première note de la gamme.",
        "8 + 7 = 15",
        "",
    ],
)
def test_french_sentences_are_kept(text: str) -> None:
    assert not written_in_english(text)


def test_no_text_of_the_reference_lessons_is_taken_for_english() -> None:
    def texts(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            return [t for v in value.values() for t in texts(v)]
        return [t for v in value for t in texts(v)] if isinstance(value, list) else []

    for path in REFERENCE:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw["analysis"]["lesson"]["subject"] in ("english", "other"):
            continue
        assert [t for t in texts(raw) if written_in_english(t)] == [], path.name


def _french_lesson() -> dict[str, Any]:
    for path in REFERENCE:
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        if raw["analysis"]["lesson"]["subject"] == "french":
            return raw
    raise AssertionError("pas de leçon de français de référence")


def test_an_english_statement_is_rejected_in_a_french_lesson() -> None:
    raw = _french_lesson()
    item = validate_analysis(raw["analysis"], raw["ocr_text"]).analysis.knowledge[0]
    material = dict(raw["material"][item.id])
    material["true_statements"] = [*material.get("true_statements", []), SEEN]

    checked = validate_material(item, material, raw["ocr_text"], Subject.FRENCH)
    assert SEEN not in checked.material.true_statements
    assert any(r.reason == ENGLISH_REASON for r in checked.rejected)
    # Dans une leçon d'anglais, la même phrase est à sa place.
    kept = validate_material(item, material, raw["ocr_text"], Subject.ENGLISH)
    assert not any(r.reason == ENGLISH_REASON for r in kept.rejected)


def test_a_notion_stated_in_english_is_rejected_in_a_french_lesson() -> None:
    raw = _french_lesson()
    analysis = json.loads(json.dumps(raw["analysis"]))
    first = analysis["knowledge"][0]
    first["statement"] = SEEN
    checked = validate_analysis(analysis, raw["ocr_text"])
    assert first["id"] not in [k.id for k in checked.analysis.knowledge]
    assert any(r.reason == ENGLISH_REASON for r in checked.rejected)
