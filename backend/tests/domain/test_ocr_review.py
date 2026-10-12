"""Étape 15 : passages douteux de la lecture d'une photo, et corrections de l'enfant."""

from app.domain.ocr_review import (
    MAX_REVIEW_ITEMS,
    Answer,
    ReviewStatus,
    Uncertain,
    apply_answers,
    select_uncertain,
)

PAGE = (
    "Le 14 juillet 1789, le peuple de Paris prend la Bastile, une prison. "
    "Il réunit les États généraux à [illisible]."
)


def test_only_verifiable_passages_are_kept() -> None:
    spans = [
        ("Bastile", "le peuple de Paris prend la Bastile, une prison"),
        ("[illisible]", "les États généraux à [illisible]"),
        ("Versailles", "les États généraux à Versailles"),  # contexte inventé : absent du texte
        ("Louis", "le peuple de Paris prend la Bastile"),  # passage absent de son contexte
        ("Bastile", "le peuple de Paris prend la Bastile, une prison"),  # doublon
        ("", "le peuple de Paris"),
    ]
    assert select_uncertain([(0, PAGE, spans)]) == [
        Uncertain(0, "Bastile", "le peuple de Paris prend la Bastile, une prison"),
        Uncertain(0, "[illisible]", "les États généraux à [illisible]"),
    ]


def test_at_most_five_passages_in_page_order() -> None:
    words = [f"mot{i}" for i in range(8)]
    page = " ".join(words)
    selected = select_uncertain(
        [(1, page, [(w, w) for w in words[4:]]), (0, page, [(w, w) for w in words[:4]])]
    )
    assert len(selected) == MAX_REVIEW_ITEMS
    assert [(u.page_index, u.text) for u in selected[:4]] == [
        (0, "mot0"),
        (0, "mot1"),
        (0, "mot2"),
        (0, "mot3"),
    ]


def test_corrections_are_applied_in_their_context_only() -> None:
    text = "la Bastile tombe. Une autre Bastile ailleurs."
    answers = [
        Answer(0, "Bastile", "la Bastile tombe", ReviewStatus.CORRECTED, "Bastille"),
        Answer(0, "tombe", "Bastile tombe", ReviewStatus.UNKNOWN),
        Answer(1, "ailleurs", "Bastile ailleurs", ReviewStatus.CORRECTED, "ici"),  # autre page
        Answer(0, "Une", "Une autre", ReviewStatus.CONFIRMED),
    ]
    assert apply_answers(0, text, answers) == "la Bastille tombe. Une autre Bastile ailleurs."
    assert apply_answers(0, text, [Answer(0, "x", "absent", ReviewStatus.CORRECTED, "y")]) == text
