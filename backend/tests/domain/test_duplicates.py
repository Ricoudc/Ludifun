"""Exercices en double (demande de la famille) : à la fin de l'analyse, le même exercice n'est
gardé qu'une fois dans la leçon ; deux exercices proches mais différents restent tous les deux."""

import pytest

from app.domain.activities.registry import ActivityRegistry
from app.domain.duplicates import deduplicate, similar
from app.domain.knowledge import KnowledgeMaterial, KnowledgeUnit, MaterialQuestion
from tests.domain.conftest import ReferenceLesson


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Le volcan crache de la lave.", "Un volcan crache de la lave."),
        ("Quel est le pluriel de cheval ?", "Quel est le pluriel de « cheval » ?"),
        ("En quelle année commence la Révolution ?", "En quelle année la Révolution commence ?"),
    ],
)
def test_the_same_text_up_to_small_words(a: str, b: str) -> None:
    assert similar(a, b)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Quel animal est un vertébré ?", "Quel animal est un invertébré ?"),
        ("Le cheval est un mammifère.", "Le chameau est un mammifère."),
        ("Combien font 7 x 8 ?", "Combien font 7 x 9 ?"),
        ("Le chat n'est pas un mammifère.", "Le chat est un mammifère."),
        ("La Révolution commence en 1789.", "La Révolution se termine en 1789."),
    ],
)
def test_one_important_word_makes_another_exercise(a: str, b: str) -> None:
    assert not similar(a, b)


def question(stem: str, answer: str) -> MaterialQuestion:
    return MaterialQuestion(difficulty=1, stem=stem, answer=answer, distractors=["A", "B", "C"])


def with_extra(
    unit: KnowledgeUnit, *questions: MaterialQuestion, truths: list[str] | None = None
) -> KnowledgeMaterial:
    m = unit.material
    return m.model_copy(
        update={
            "questions": [*m.questions, *questions],
            "true_statements": [*m.true_statements, *(truths or [])],
        }
    )


def always(_: str, __: KnowledgeMaterial) -> bool:
    return True


def test_the_same_question_in_two_notions_is_kept_once(history: ReferenceLesson) -> None:
    first, second = list(history.units.values())[:2]
    shared = question("Quel bâtiment parisien est pris le 14 juillet 1789 ?", "La Bastille")
    near = question("Le 14 juillet 1789, quel bâtiment parisien est pris ?", "la Bastille")
    other_answer = question("Quel bâtiment parisien est pris le 14 juillet 1789 ?", "Le Louvre")
    result = deduplicate(
        [
            (first.id, with_extra(first, shared, truths=["Le roi réunit les États généraux."])),
            (
                second.id,
                with_extra(second, near, other_answer, truths=["Le roi réunit les états généraux !"]),
            ),
        ],
        always,
    )
    assert shared in result[first.id].material.questions  # la notion la plus importante garde le sien
    kept = result[second.id].material
    assert near not in kept.questions and other_answer in kept.questions  # une autre réponse : autre exercice
    assert "Le roi réunit les états généraux !" not in kept.true_statements
    reasons = [r.reason for r in result[second.id].removed]
    assert len(reasons) == 2 and all(f"notion {first.id}" in r for r in reasons)
    assert result[first.id].removed == []


def test_a_duplicate_inside_one_notion_is_removed(history: ReferenceLesson) -> None:
    unit = next(iter(history.units.values()))
    twice = with_extra(unit, question("Qui réunit les États généraux ?", "Louis XVI"))
    twice = with_extra(
        KnowledgeUnit(item=unit.item, material=twice),
        question("Qui réunit les États généraux ?", "Louis XVI"),
    )
    result = deduplicate([(unit.id, twice)], always)[unit.id]
    assert sum(q.stem == "Qui réunit les États généraux ?" for q in result.material.questions) == 1
    assert "même notion" in result.removed[0].reason


def test_a_notion_never_loses_all_its_games(history: ReferenceLesson, registry: ActivityRegistry) -> None:
    """Sans ses doublons, la seconde notion n'aurait plus rien à jouer : elle les garde."""
    first, second = list(history.units.values())[:2]
    only = second.material.model_copy(
        update={
            "questions": list(first.material.questions),
            "true_statements": [],
            "false_statements": [],
            "cloze": None,
            "pair": None,
            "flashcard": None,
            "open_questions": [],
            "sorting": None,
            "sequence": None,
            "spelling": None,
        }
    )

    def usable(notion: str, material: KnowledgeMaterial) -> bool:
        item = history.units[notion].item
        return bool(registry.single_options(KnowledgeUnit(item=item, material=material)))

    result = deduplicate([(first.id, first.material), (second.id, only)], usable)
    assert result[second.id].material == only and result[second.id].removed == []


def test_a_new_version_is_checked_against_the_other_notions(history: ReferenceLesson) -> None:
    """Correction demandée par le parent : rien de ce que l'enfant voit déjà ailleurs."""
    first, second = list(history.units.values())[:2]
    copied = first.material.questions[0]
    new = with_extra(second, copied)
    result = deduplicate([(second.id, new)], always, already=[(first.id, first.material)])[second.id]
    assert copied not in result.material.questions
    assert result.removed and "notion" in result.removed[0].reason
