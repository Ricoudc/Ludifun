import copy
from typing import Any

import pytest

from app.domain.knowledge import KnowledgeItem
from app.domain.validation import (
    PICTURE_REASON,
    AnalysisError,
    needs_picture,
    validate_analysis,
    validate_material,
)
from tests.domain.conftest import ReferenceLesson

# --------------------------------------------------------------------------- #
# Leçons de référence : entièrement valides
# --------------------------------------------------------------------------- #


def test_reference_lessons_are_fully_valid(lesson: ReferenceLesson) -> None:
    validation = validate_analysis(lesson.raw["analysis"], lesson.raw["ocr_text"])
    assert validation.rejected == []
    assert validation.analysis.warnings == []
    assert len(validation.analysis.knowledge) == len(lesson.raw["analysis"]["knowledge"])
    for item in validation.analysis.knowledge:
        material = validate_material(item, lesson.raw["material"][item.id])
        assert material.rejected == [], (item.id, material.rejected)
        assert material.rejection_rate == 0


# --------------------------------------------------------------------------- #
# Analyse
# --------------------------------------------------------------------------- #


def _analysis(history: ReferenceLesson) -> dict[str, Any]:
    return copy.deepcopy(history.raw["analysis"])


def test_not_a_lesson(history: ReferenceLesson) -> None:
    result = validate_analysis({"is_lesson": False}, "une photo de chat")
    assert result.analysis.is_lesson is False
    assert result.analysis.knowledge == []


@pytest.mark.parametrize(
    "raw",
    [{}, {"is_lesson": "oui"}, {"is_lesson": True, "lesson": {"subject": "history"}}],
)
def test_unusable_analysis_raises(raw: dict[str, Any]) -> None:
    with pytest.raises(AnalysisError):
        validate_analysis(raw, "texte")


def test_invented_notion_is_rejected(history: ReferenceLesson) -> None:
    raw = _analysis(history)
    raw["knowledge"][1]["source_excerpt"] = "Louis XVI s'enfuit à Varennes en 1791"
    result = validate_analysis(raw, history.raw["ocr_text"])
    assert [r.element for r in result.rejected] == ["k2"]
    assert "introuvable" in result.rejected[0].reason
    assert "k2" not in {k.id for k in result.analysis.knowledge}


def test_ocr_typos_do_not_reject_a_notion(history: ReferenceLesson) -> None:
    ocr = history.raw["ocr_text"].replace("prend la Bastille", "prend la BastiIle")
    result = validate_analysis(_analysis(history), ocr)
    assert result.rejected == []


@pytest.mark.parametrize(
    "change, reason",
    [
        ({"importance": 6}, "importance"),
        ({"id": "notion-1"}, "id"),
        ({"type": "animal"}, "type"),
        ({"label": "  "}, "label"),
    ],
)
def test_invalid_notion_is_rejected(history: ReferenceLesson, change: dict[str, Any], reason: str) -> None:
    raw = _analysis(history)
    raw["knowledge"][0].update(change)
    result = validate_analysis(raw, history.raw["ocr_text"])
    assert len(result.rejected) == 1
    assert reason in result.rejected[0].reason
    assert len(result.analysis.knowledge) == len(raw["knowledge"]) - 1


def test_incomplete_attributes_keep_the_notion(history: ReferenceLesson) -> None:
    """Petit modèle qui oublie un champ : la notion est gardée (texte repris de la phrase à
    retenir, ou simple fait), avec un avertissement, au lieu d'être perdue."""
    raw = _analysis(history)
    date, term = raw["knowledge"][0], next(k for k in raw["knowledge"] if k["type"] == "term")
    date["attributes"] = {"precision": "year", "event": "Début"}  # date sans valeur
    term["attributes"] = {}  # mot sans définition
    result = validate_analysis(raw, history.raw["ocr_text"])
    assert result.rejected == []
    kept = {k.id: k for k in result.analysis.knowledge}
    assert kept[date["id"]].type == "fact" and kept[date["id"]].attributes == {}
    assert kept[term["id"]].type == "term"
    assert kept[term["id"]].attributes["definition"] == term["statement"]
    warnings = " ".join(result.analysis.warnings)
    assert "gardée comme simple fait" in warnings and "repris de la phrase à retenir" in warnings


def test_duplicate_notion_id_is_rejected(history: ReferenceLesson) -> None:
    raw = _analysis(history)
    raw["knowledge"][1]["id"] = "k1"
    result = validate_analysis(raw, history.raw["ocr_text"])
    assert [(r.element, r.reason) for r in result.rejected] == [("k1", "identifiant en double")]


def test_relation_to_rejected_notion_is_removed(history: ReferenceLesson) -> None:
    raw = _analysis(history)
    raw["knowledge"][0]["source_excerpt"] = "texte inventé"  # k1 rejetée
    result = validate_analysis(raw, history.raw["ocr_text"])
    bastille = result.analysis.item("k4")
    assert bastille.relations == []
    assert any("k4" in w for w in result.analysis.warnings)


# --------------------------------------------------------------------------- #
# Matériel
# --------------------------------------------------------------------------- #


def _material(history: ReferenceLesson, knowledge_id: str = "k1") -> tuple[KnowledgeItem, dict[str, Any]]:
    return history.analysis.item(knowledge_id), copy.deepcopy(history.raw["material"][knowledge_id])


def _reasons(item: KnowledgeItem, raw: dict[str, Any]) -> dict[str, str]:
    return {r.element: r.reason for r in validate_material(item, raw).rejected}


def test_distractor_equal_to_answer_is_dropped(history: ReferenceLesson) -> None:
    item, raw = _material(history)
    raw["questions"][0]["distractors"] = ["1492", "1789", "1914", "1848"]
    result = validate_material(item, raw)
    assert result.rejected == []
    assert result.material.questions[0].distractors == ["1492", "1914", "1848"]


@pytest.mark.parametrize(
    "distractors",
    [
        ["1492", "1789", "1914"],  # un doublon de la réponse → 2 restants
        ["1492", "1492", "1914"],  # doublon
        ["1492", "La Renaissance", "1914"],  # nature différente d'une année
    ],
)
def test_question_without_three_valid_distractors_is_rejected(
    history: ReferenceLesson, distractors: list[str]
) -> None:
    item, raw = _material(history)
    raw["questions"][0]["distractors"] = distractors
    assert "3 distracteurs" in _reasons(item, raw)["questions[0]"]


def test_question_whose_stem_gives_the_answer_is_rejected(history: ReferenceLesson) -> None:
    item, raw = _material(history)
    raw["questions"][0]["stem"] = "La Révolution commence en 1789 : vrai ?"
    assert _reasons(item, raw)["questions[0]"] == "l'énoncé contient la réponse"


@pytest.mark.parametrize(
    "false_statement, reason",
    [
        ("La Révolution française commence en 1789.", "identique"),
        ("La Révolution française ne commence pas en 1789.", "négation"),
    ],
)
def test_bad_false_statement_is_rejected(history: ReferenceLesson, false_statement: str, reason: str) -> None:
    item, raw = _material(history)
    raw["false_statements"] = [false_statement]
    assert reason in _reasons(item, raw)["false_statements[0]"]


@pytest.mark.parametrize(
    "cloze, reason",
    [
        ({"text": "La Révolution française commence en 1789.", "answers": ["1789"]}, "exactement un"),
        ({"text": "La ___ commence en ___.", "answers": ["Révolution"]}, "exactement un"),
        ({"text": "En 1789, la Révolution commence en ___.", "answers": ["1789"]}, "ailleurs"),
        ({"text": "La Révolution commence en ___.", "answers": []}, "answers"),
    ],
)
def test_bad_cloze_is_rejected(history: ReferenceLesson, cloze: dict[str, Any], reason: str) -> None:
    item, raw = _material(history)
    raw["cloze"] = cloze
    assert reason in _reasons(item, raw)["cloze"]


def test_pair_and_flashcard_checks(history: ReferenceLesson) -> None:
    item, raw = _material(history)
    raw["pair"] = {"left": "1789", "right": "x" * 61}
    raw["flashcard"] = {"front": "1789", "back": "1789"}
    reasons = _reasons(item, raw)
    assert "right" in reasons["pair"]
    assert reasons["flashcard"] == "recto et verso identiques"


@pytest.mark.parametrize(
    "tip, reason",
    [
        ("x" * 121, "trop longue"),
        ("1789 = début de la Révolution, et 1793 = la Terreur.", "nombre absent"),
        ("1789 : pense à Napoléon.", "nom propre absent"),
    ],
)
def test_tip_that_invents_something_is_rejected(history: ReferenceLesson, tip: str, reason: str) -> None:
    item, raw = _material(history)
    raw["tip"] = tip
    assert reason in _reasons(item, raw)["tip"]


def test_missing_explanation_falls_back_to_statement(history: ReferenceLesson) -> None:
    item, raw = _material(history)
    del raw["explanation"]
    result = validate_material(item, raw)
    assert result.material.explanation == item.statement
    assert [r.element for r in result.rejected] == ["explanation"]


def test_rejection_rate(history: ReferenceLesson) -> None:
    item, raw = _material(history)
    raw["tip"] = "x" * 200
    raw["false_statements"] = [item.statement]
    result = validate_material(item, raw)
    # Conservés : 2 questions, 1 vraie, cloze, paire, carte = 6 ; rejetés : 2.
    assert result.rejection_rate == pytest.approx(2 / 8)


@pytest.mark.parametrize(
    "change",
    [
        {
            "questions": [
                {
                    "difficulty": 1,
                    "stem": "Sur le dessin, quel animal vole ?",
                    "answer": "L'aigle",
                    "distractors": ["Le chat", "Le chien", "La vache"],
                }
            ]
        },
        {"true_statements": ["Observe le schéma : l'eau s'évapore."]},
        {"cloze": {"text": "L'image ci-dessus montre un ___.", "answers": ["volcan"]}},
        {"flashcard": {"front": "Que montre la photo ?", "back": "Un volcan"}},
    ],
)
def test_elements_that_need_the_lesson_picture_are_rejected(
    history: ReferenceLesson, change: dict[str, Any]
) -> None:
    """Les photos ne sont jamais gardées : une question sur une image serait impossible."""
    item = history.analysis.knowledge[0]
    result = validate_material(item, {"explanation": "x", **change})
    assert any(r.reason == PICTURE_REASON for r in result.rejected)
    material = result.material
    assert not (material.questions or material.true_statements or material.cloze or material.flashcard)


def test_a_geometric_figure_is_not_a_picture() -> None:
    assert not needs_picture("Quelle figure a quatre côtés égaux ?")
    assert needs_picture("Regarde l'illustration.")
