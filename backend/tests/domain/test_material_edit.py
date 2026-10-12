"""§5.59 : le parent corrige lui-même une question de la leçon (« Nous ___ contents. » :
réponse retenue « avons », le parent la remplace par « sommes »)."""

import random

import pytest

from app.domain.activities.base import ActivityCode
from app.domain.activities.registry import ActivityRegistry
from app.domain.knowledge import (
    Cloze,
    Flashcard,
    Grade,
    KnowledgeItem,
    KnowledgeMaterial,
    KnowledgeType,
    KnowledgeUnit,
    MaterialQuestion,
    Pair,
    Subject,
)
from app.domain.material_edit import Edit, EditError, apply_edit, editables, locate

STEM = 'Quel verbe va avec "Nous ___ contents." ?'


def material() -> KnowledgeMaterial:
    return KnowledgeMaterial(
        knowledge_id="k1",
        explanation="Relis la leçon.",
        questions=[
            MaterialQuestion(
                difficulty=1,
                stem=STEM,
                answer="avons",
                distractors=["sommes", "êtes", "sont"],
                misconceptions=["confusion être / avoir", None, None],
            ),
            MaterialQuestion(
                difficulty=1, stem="2 + 2 ?", answer="4", distractors=["3", "5", "6"], generated=True
            ),
        ],
        true_statements=["Nous sommes contents."],
        false_statements=["Nous avons contents."],
        cloze=Cloze(text="Nous ___ contents.", answers=["avons"]),
        pair=Pair(left="nous", right="avons"),
        flashcard=Flashcard(front="être, nous", back="avons"),
    )


def unit(m: KnowledgeMaterial) -> KnowledgeUnit:
    item = KnowledgeItem(
        id="k1",
        type=KnowledgeType.RULE,
        label="Le verbe être au présent",
        statement="Nous sommes contents.",
        importance=4,
        source_excerpt="Nous sommes",
        attributes={"statement": "Nous sommes.", "example": "Nous sommes à l'école."},
    )
    return KnowledgeUnit(item=item, material=m, subject=Subject.FRENCH, grade=Grade.CE1)


def test_everything_the_parent_can_correct_is_listed() -> None:
    found = editables(material())
    assert [(e.kind, e.index) for e in found] == [
        ("question", 0),  # la question calculée par le code n'est pas corrigeable
        ("statement", 0),
        ("statement", 1),
        ("cloze", 0),
        ("pair", 0),
        ("flashcard", 0),
    ]
    assert found[0].answer == "avons" and found[0].distractors == ["sommes", "êtes", "sont"]
    assert [e.true for e in found[1:3]] == [True, False]


def test_the_parent_fixes_the_answer_of_a_question() -> None:
    fixed = apply_edit(
        material(),
        Edit("question", 0, before=STEM, text=STEM, answer="sommes", distractors=["avons", "êtes", "sont"]),
    )
    question = fixed.questions[0]
    assert question.answer == "sommes" and question.distractors == ["avons", "êtes", "sont"]
    # Les erreurs typiques des anciennes mauvaises réponses ne valent plus.
    assert question.misconceptions == []
    assert fixed.questions[1] == material().questions[1]  # le reste ne bouge pas
    # Seul l'énoncé change : les erreurs typiques restent.
    reworded = apply_edit(
        material(),
        Edit(
            "question",
            0,
            before=STEM,
            text="Complète : Nous ___ contents.",
            answer="avons",
            distractors=["sommes", "êtes", "sont"],
        ),
    )
    assert reworded.questions[0].misconceptions == ["confusion être / avoir", None, None]


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (
            Edit(
                "question", 0, before="Autre chose", text=STEM, answer="sommes", distractors=["a", "b", "c"]
            ),
            "a changé entre-temps",
        ),
        (
            Edit("question", 5, before=STEM, text=STEM, answer="sommes", distractors=["a", "b", "c"]),
            "a changé entre-temps",
        ),
        (Edit("question", 0, before=STEM, text="  ", answer="sommes", distractors=["a", "b", "c"]), "vide"),
        (
            Edit("question", 0, before=STEM, text=STEM, answer="", distractors=["a", "b", "c"]),
            "bonne réponse",
        ),
        (Edit("question", 0, before=STEM, text=STEM, answer="sommes", distractors=["a", "b"]), "trois"),
        (
            Edit("question", 0, before=STEM, text=STEM, answer="sommes", distractors=["Sommes", "b", "c"]),
            "différentes",
        ),
        (
            Edit("statement", 0, before="Nous sommes contents.", text="Nous sommes contents."),
            "vraie ou fausse",
        ),
        (
            Edit("cloze", 0, before="Nous ___ contents.", text="Nous sommes contents.", answers=["x"]),
            "« ___ »",
        ),
        (Edit("cloze", 0, before="Nous ___ contents.", text="Nous ___ contents.", answers=[" "]), "réponse"),
        (Edit("pair", 0, before="nous", text="nous", answer=""), "deux côtés"),
        (Edit("pair", 0, before="nous", text="x" * 41, answer="avons"), "pas valable"),
        (Edit("flashcard", 0, before="être, nous", text="être, nous"), "recto"),
    ],
)
def test_a_bad_correction_is_refused(edit: Edit, message: str) -> None:
    with pytest.raises(EditError, match=message):
        apply_edit(material(), edit)


def test_statements_cloze_pair_and_flashcard() -> None:
    m = apply_edit(
        material(), Edit("statement", 1, before="Nous avons contents.", text="Nous avons faim.", true=True)
    )
    assert m.true_statements == ["Nous sommes contents.", "Nous avons faim."] and m.false_statements == []
    m = apply_edit(
        material(),
        Edit("cloze", 0, before="Nous ___ contents.", text="Nous ___ contents.", answers=["sommes"]),
    )
    assert m.cloze == Cloze(text="Nous ___ contents.", answers=["sommes"])
    m = apply_edit(material(), Edit("pair", 0, before="nous", text="nous", answer="sommes"))
    assert m.pair == Pair(left="nous", right="sommes")
    m = apply_edit(material(), Edit("flashcard", 0, before="être, nous", text="être, nous", answer="sommes"))
    assert m.flashcard == Flashcard(front="être, nous", back="sommes")


def test_a_reported_activity_is_found_in_the_material(registry: ActivityRegistry) -> None:
    """Depuis une question signalée, le parent retrouve l'élément à corriger."""
    m, lesson = material(), unit(material())
    for code, kind in (
        (ActivityCode.MCQ, "question"),
        (ActivityCode.TRUE_FALSE, "statement"),
        (ActivityCode.FILL_BLANK, "cloze"),
        (ActivityCode.FLASHCARD, "flashcard"),
    ):
        game = registry.get(code)
        for seed in range(10):
            activity = game.build([lesson], min(game.difficulties), random.Random(seed))
            hit = locate(m, activity)
            if code == ActivityCode.MCQ and activity.payload.get("prompt") == "2 + 2 ?":
                continue
            assert hit is not None and hit.kind == kind, (code, activity.payload)
