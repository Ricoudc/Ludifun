"""Justesse des corrections : une bonne réponse écrite autrement est juste, une faute ne passe
jamais pour juste, et une question qui aurait deux bonnes réponses n'est pas posée."""

import random
from dataclasses import replace
from typing import Any

import pytest

from app.domain.activities.registry import ActivityRegistry
from app.domain.activities.spelling import same_spelling
from app.domain.equivalence import (
    all_different,
    consistent,
    french_number,
    same_answer,
    separate_boxes,
    statement_truth,
    written_match,
)
from app.domain.knowledge import (
    KnowledgeItem,
    KnowledgeMaterial,
    KnowledgeType,
    KnowledgeUnit,
    Subject,
)
from app.domain.validation import validate_material


@pytest.mark.parametrize(
    "given, expected",
    [
        ("0.50", "0,5"),  # point ou virgule, zéro final
        ("1000", "1 000"),  # espace des milliers
        ("1 000", "1000"),  # espace insécable
        ("8 + 7", "7 + 8"),  # l'addition se lit dans les deux sens
        ("8+7", "7 + 8"),
        ("3 × 4", "4 x 3"),
        ("-3", "−3"),  # signe moins typographique
        ("quinze", "15"),  # nombre en lettres
        ("15", "quinze"),
        ("dix-sept", "17"),
        ("soixante et onze", "71"),
        ("quatre-vingt-dix-neuf", "99"),
        ("deux mille vingt-six", "2026"),
        ("15cm", "15 cm"),  # unité collée
        ("3h30", "3 h 30"),
        ("14 juilet 1789", "14 juillet 1789"),  # une faute de frappe, pas sur le nombre
        ("revolusion", "Révolution"),
        ("porte monnaie", "porte-monnaie"),
    ],
)
def test_the_same_answer_written_otherwise_is_right(given: str, expected: str) -> None:
    assert written_match(given, expected)


@pytest.mark.parametrize(
    "given, expected",
    [
        ("en 1788", "en 1789"),  # une faute de frappe ne change jamais un nombre
        ("14 juillet 1798", "14 juillet 1789"),
        ("3", "-3"),  # ni un signe
        ("7 - 8", "7 + 8"),
        ("15", "16"),
        ("15", "15 cm"),  # l'unité manque
        ("1/2", "0,5"),  # autre écriture demandée
        ("8 + 6", "7 + 7"),  # même valeur, autre calcul
        ("", "chat"),
    ],
)
def test_a_mistake_is_never_taken_for_right(given: str, expected: str) -> None:
    assert not written_match(given, expected)


@pytest.mark.parametrize(
    "given, expected, right",
    [
        ("chanté", "chanté", True),
        ("Chanté.", "chanté", True),  # majuscule et point
        ("coeur", "cœur", True),  # « oe » au clavier du téléphone
        ("c’est", "c'est", True),
        ("chanter", "chanté", False),  # é / er : c'est ce qui est appris
        ("a", "à", False),
        ("ecrire", "écrire", False),
        ("verte", "vert", False),
        ("15", "quinze", False),  # écrire les nombres en lettres
    ],
)
def test_in_french_the_spelling_counts(given: str, expected: str, right: bool) -> None:
    assert written_match(given, expected, exact_spelling=True) is right


def test_the_instruction_can_ask_for_letters_or_digits() -> None:
    assert not written_match("15", "quinze", context="Écris en lettres : 15 → ___")
    assert not written_match("quinze", "15", context="Écris le nombre en chiffres : quinze → ___")
    assert written_match("quinze", "15", context="7 + 8 = ___")


def test_french_numbers() -> None:
    assert [french_number(t) for t in ["zéro", "vingt et un", "quatre-vingts", "cent un", "mille"]] == [
        0,
        21,
        80,
        101,
        1000,
    ]
    assert french_number("trois cent quarante-cinq") == 345
    assert french_number("septante") == 70  # Belgique, Suisse
    assert french_number("le chat") is None


def test_two_choices_that_say_the_same_thing() -> None:
    assert same_answer("8 + 7", "7 + 8")
    assert same_answer("1/2", "0,5")
    assert same_answer("2/4", "1/2")
    assert same_answer("quinze", "15")
    assert same_answer("Paris", "paris.")
    assert not same_answer("14", "15")
    assert not same_answer("un", "une")  # deux articles, pas deux nombres
    assert not same_answer("Paris", "Lyon")


def test_a_calculation_statement_is_checked() -> None:
    assert statement_truth("8 + 7 = 15") is True
    assert statement_truth("7 × 8 = 56.") is True
    assert statement_truth("7 + 8 = 16") is False
    assert statement_truth("La somme de 7 et 8 vaut 15.") is None  # la leçon tranche


def test_ties_in_orders_and_boxes() -> None:
    assert not all_different(["0,5", "1/2", "3"])
    assert all_different(["1/4", "1/2", "3"])
    assert separate_boxes([["0,5", "2/4"], ["0,25", "1/8"]])  # même valeur dans la même case
    assert not separate_boxes([["0,5", "1/4"], ["2/4", "1/8"]])


def calculation_item() -> KnowledgeItem:
    return KnowledgeItem(
        id="k1",
        type=KnowledgeType.FORMULA,
        label="L'addition",
        statement="7 + 8 = 15",
        importance=5,
        attributes={"expression": "7 + 8 = 15"},
        source_excerpt="7 + 8 = 15",
    )


def question(answer: str, distractors: list[str]) -> dict[str, Any]:
    return {"stem": "Quel calcul donne 15 ?", "answer": answer, "distractors": distractors, "difficulty": 1}


def test_the_ai_cannot_propose_a_second_right_answer() -> None:
    checked = validate_material(
        calculation_item(),
        {
            "explanation": "L'ordre des nombres ne change pas une somme.",
            "questions": [question("7 + 8", ["8 + 7", "7 + 9", "6 + 8"])],
            "true_statements": ["7 + 8 = 16", "8 + 7 = 15"],
            "false_statements": ["8 + 7 = 15", "7 + 9 = 15"],
            "sequence": {"prompt": "Du plus petit au plus grand.", "items": ["0,5", "1/2", "3"]},
        },
    )
    material = checked.material
    assert material.questions == []  # 2 distracteurs valables seulement
    assert material.true_statements == ["8 + 7 = 15"]
    assert material.false_statements == ["7 + 9 = 15"]
    assert material.sequence is None
    reasons = {r.reason for r in checked.rejected}
    assert {"calcul faux donné pour vrai", "calcul juste donné pour faux"} <= reasons


def test_lessons_analysed_before_the_checks_are_cleaned_when_played() -> None:
    material = KnowledgeMaterial.model_validate(
        {
            "knowledge_id": "k1",
            "explanation": "L'ordre des nombres ne change pas une somme.",
            "questions": [
                question("7 + 8", ["8 + 7", "7 + 9", "6 + 8"]),
                question("15", ["14", "16", "17"]),
            ],
            "true_statements": ["7 + 8 = 15", "7 + 8 = 16"],
            "false_statements": ["8 + 7 = 15", "7 + 9 = 15"],
            "sequence": {"prompt": "Du plus petit au plus grand.", "items": ["0,5", "1/2", "3"]},
        }
    )
    cleaned = consistent(material)
    assert [q.answer for q in cleaned.questions] == ["15"]
    assert cleaned.true_statements == ["7 + 8 = 15"]
    assert cleaned.false_statements == ["7 + 9 = 15"]
    assert cleaned.sequence is None
    good = consistent(cleaned)
    assert good is cleaned  # rien à retirer : le même objet


def cloze_unit(subject: Subject | None, text: str, answer: str) -> KnowledgeUnit:
    item = KnowledgeItem(
        id="k1",
        type=KnowledgeType.RULE,
        label="Le participe passé",
        statement="Après avoir, le verbe en -er s'écrit é.",
        importance=5,
        attributes={"statement": "Après avoir, on écrit é.", "example": "Il a chanté."},
        source_excerpt="Après avoir, le verbe en -er s'écrit é.",
    )
    material = KnowledgeMaterial.model_validate(
        {"knowledge_id": "k1", "explanation": "Avoir + é.", "cloze": {"text": text, "answers": [answer]}}
    )
    return KnowledgeUnit(item=item, material=material, subject=subject)


def test_fill_blank_in_french_wants_the_exact_spelling(registry: ActivityRegistry) -> None:
    fill = registry.get("FILL_BLANK")
    french = fill.build([cloze_unit(Subject.FRENCH, "Il a ___ une chanson.", "chanté")], 2, random.Random(0))
    assert fill.grade(french, {"text": "chanter"}).score == 0
    assert fill.grade(french, {"text": "Chanté"}).score == 1
    history = fill.build(
        [cloze_unit(Subject.HISTORY, "Il a ___ une chanson.", "chanté")], 2, random.Random(0)
    )
    assert fill.grade(history, {"text": "chanter"}).score == 1  # une faute de frappe, hors français


def test_fill_blank_in_maths_accepts_another_writing(registry: ActivityRegistry) -> None:
    fill = registry.get("FILL_BLANK")
    math = fill.build([cloze_unit(Subject.MATH, "La moitié de 1 s'écrit ___.", "0,5")], 2, random.Random(0))
    assert fill.grade(math, {"text": "0.50"}).score == 1
    assert fill.grade(math, {"text": "0,6"}).score == 0
    # Une activité construite avant ce réglage (sans « exact_spelling ») se corrige comme avant.
    old = replace(math, solution={k: v for k, v in math.solution.items() if k != "exact_spelling"})
    assert fill.grade(old, {"text": "0,5"}).score == 1


def test_spelling_games_accept_the_phone_keyboard() -> None:
    assert same_spelling("coeur", "cœur")
    assert same_spelling("Cœur.", "cœur")
    assert not same_spelling("coeurs", "cœur")
    assert not same_spelling("ecole", "école")
