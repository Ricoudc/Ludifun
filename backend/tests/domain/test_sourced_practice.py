"""Étape 29 : questions tirées des sites de confiance. L'IA propose, le code ne garde que ce que
la page prouve (citation exacte qui contient la réponse), qui parle de la notion et se comprend
seul ; la question garde sa source, montrée à l'enfant et au parent (§117)."""

import random

from app.domain.activities.base import ActivityCode
from app.domain.activities.registry import ActivityRegistry
from app.domain.knowledge import KnowledgeItem, KnowledgeUnit
from app.domain.material_view import material_blocks
from app.domain.sourced_practice import ProposedQuestion, check_practice
from app.domain.sources import Excerpt
from tests.domain.conftest import ReferenceLesson

PAGE = "https://fr.vikidia.org/wiki/Vert%C3%A9br%C3%A9"
EXCERPTS = [
    Excerpt(
        1,
        PAGE,
        "Vertébré — Vikidia",
        "Les vertébrés sont des animaux qui possèdent un squelette interne. Le lézard est un "
        "vertébré qui pond des œufs. La baleine est un mammifère vertébré qui vit dans la mer.",
    )
]
ITEM = KnowledgeItem(
    id="k1",
    type="term",
    label="Les vertébrés",
    statement="Les vertébrés sont des animaux qui ont un squelette avec une colonne vertébrale.",
    importance=5,
    attributes={"definition": "animaux avec une colonne vertébrale"},
    source_excerpt="Les vertébrés ont une colonne vertébrale.",
)


def proposed(**changes: object) -> ProposedQuestion:
    base: dict[str, object] = {
        "stem": "Quel animal vertébré vit dans la mer ?",
        "answer": "La baleine",
        "distractors": ["Le ver de terre", "La méduse", "L'escargot"],
        "difficulty": 1,
        "source": 1,
        "quote": "La baleine est un mammifère vertébré qui vit dans la mer.",
    }
    return ProposedQuestion(**{**base, **changes})  # type: ignore[arg-type]


def test_a_proven_question_is_kept_with_its_source() -> None:
    checked = check_practice(ITEM, [proposed()], EXCERPTS)
    assert checked.rejected == []
    [question] = checked.questions
    assert question.answer == "La baleine" and question.source is not None
    assert question.source.site == "fr.vikidia.org" and question.source.url == PAGE
    assert question.source.quote == "La baleine est un mammifère vertébré qui vit dans la mer."


def test_only_what_the_page_proves() -> None:
    cases = {
        "citation absente": proposed(quote="La baleine est le plus gros poisson de la mer."),
        "mauvais extrait": proposed(source=2),
        "réponse absente de la citation": proposed(
            answer="Le dauphin", distractors=["A ver", "B ver", "C ver"]
        ),
        "réponse dans l'énoncé": proposed(stem="La baleine est-elle un vertébré qui vit dans la mer ?"),
        "autre exemple de la notion, gardé": proposed(
            stem="Qui pond des œufs ?",
            answer="Le lézard",
            distractors=["Le chat", "Le chien", "La vache"],
            quote="Le lézard est un vertébré qui pond des œufs.",
        ),
        "renvoie à la page": proposed(stem="D'après le texte, quel animal vit dans la mer ?"),
    }
    checked = check_practice(ITEM, list(cases.values()), EXCERPTS)
    reasons = [r.reason for r in checked.rejected]
    assert len(reasons) == 5 and len(checked.questions) == 1, reasons
    assert any("citation absente" in r for r in reasons)
    assert any("ne contient pas la bonne réponse" in r for r in reasons)
    assert any("énoncé contient la réponse" in r for r in reasons)


def test_off_topic_questions_are_refused() -> None:
    other = ITEM.model_copy(update={"label": "Les volcans", "statement": "Un volcan crache de la lave."})
    checked = check_practice(other, [proposed()], EXCERPTS)
    assert checked.questions == [] and "ne parle pas de la notion" in checked.rejected[0].reason


def test_at_most_a_few_questions_per_notion() -> None:
    same_twice = [proposed(), proposed(stem="Quel vertébré vit dans la mer ?")]
    checked = check_practice(ITEM, same_twice, EXCERPTS, limit=1)
    assert len(checked.questions) == 1 and "plus de 1" in checked.rejected[0].reason


def test_the_child_sees_where_the_question_comes_from(
    history: ReferenceLesson, registry: ActivityRegistry
) -> None:
    unit = next(iter(history.units.values()))
    [question] = check_practice(ITEM, [proposed()], EXCERPTS).questions
    sourced = KnowledgeUnit(
        item=unit.item,
        material=unit.material.model_copy(
            update={"questions": [question.model_copy(update={"difficulty": 1})]}
        ),
    )
    activity = registry.get(ActivityCode.MCQ).build([sourced], 1, random.Random(1))
    assert activity.payload["source"] == "fr.vikidia.org"
    assert activity.solution["explanation"] == (
        "D'après fr.vikidia.org : « La baleine est un mammifère vertébré qui vit dans la mer. »"
    )
    for code in (ActivityCode.WHEEL, ActivityCode.BOX):  # aussi dans les jeux de hasard
        game = registry.get(code)
        assert game.accepts(sourced)
    # Le parent voit les questions des sites à part, avec la phrase qui prouve la réponse.
    blocks = {b.title: b.lines for b in material_blocks(sourced.material)}
    assert "📚 Questions tirées des sites de confiance" in blocks
    assert "D'après fr.vikidia.org" in blocks["📚 Questions tirées des sites de confiance"][0]
