"""L'enfant révise sans la fiche (photo prise dans un cahier, sur Internet…) : une question qui y
renvoie est sans réponse possible. Les données passent dans la question, ou un passage de la
leçon, recopié, est montré avec elle.

Cas réel : fiche « Singulier et pluriel » (entoure les mots au pluriel, colorie le bon article,
écris au singulier ou au pluriel).
"""

import random

from app.domain.activities.mcq import Mcq
from app.domain.activities.open_question import OpenQuestionActivity
from app.domain.knowledge import KnowledgeItem, KnowledgeType, KnowledgeUnit
from app.domain.material_view import material_blocks
from app.domain.validation import PASSAGE_REASON, SUPPORT_REASON, needs_support, validate_material

FICHE = (
    "Entoure les mots au pluriel. des lapins un sapin les choux la feuille l'éléphant une cerise "
    "des plantes l'écureuil. Colorie les bons articles. la les maisons un des poisson. "
    "Écris les mots au singulier ou au pluriel. une feuille → le citron →"
)
RECIT = (
    "Le Petit Chaperon rouge part chez sa grand-mère avec une galette et un petit pot de beurre. "
    "Dans le bois, elle rencontre le loup."
)


def item(excerpt: str = "des lapins un sapin les choux") -> KnowledgeItem:
    return KnowledgeItem(
        id="k1",
        type=KnowledgeType.RULE,
        label="Le pluriel des noms",
        statement="Devant un nom au pluriel, on écrit les ou des : des lapins, les choux.",
        importance=5,
        attributes={"statement": "Au pluriel : les, des.", "example": "des lapins"},
        source_excerpt=excerpt,
    )


def mcq(stem: str, answer: str, distractors: list[str], passage: str | None = None) -> dict[str, object]:
    return {"stem": stem, "answer": answer, "distractors": distractors, "difficulty": 1, "passage": passage}


def test_references_to_the_sheet_are_detected() -> None:
    for text in [
        "D'après le texte, où va le Petit Chaperon rouge ?",
        "Quels mots de cette liste sont au pluriel ?",
        "Dans le tableau, quel article va avec maisons ?",
        "Que fait le loup dans l'histoire lue en classe ?",
        "Recopie la réponse de l'exercice 2.",
        "Colorie les bonnes étiquettes dans les cases.",
    ]:
        assert needs_support(text), text
    for text in [
        "Le mot « des lapins » est-il au singulier ou au pluriel ?",
        "Quel article va avec « maisons » ?",
        "Dans l'histoire de France, qui est Clovis ?",
        "Sur une carte, le nord est en haut.",
        "Le conte est un type de texte.",
    ]:
        assert not needs_support(text), text


def test_worksheet_questions_must_carry_their_data() -> None:
    raw = {
        "explanation": "Au pluriel, on écrit les ou des devant le nom.",
        "questions": [
            mcq(
                "Quels mots de la liste sont au pluriel ?",
                "des lapins",
                ["un sapin", "la feuille", "une cerise"],
            ),
            mcq("Quel article va avec « maisons » ?", "les", ["la", "un", "une"]),
        ],
        "true_statements": [
            "Dans l'exercice 1, des lapins est au pluriel.",
            "« Des plantes » est au pluriel.",
        ],
        "false_statements": ["« Un sapin » est au pluriel."],
        "cloze": {"text": "Sur la fiche, une feuille devient des ___.", "answers": ["feuilles"]},
        "flashcard": {"front": "Le pluriel des mots du tableau", "back": "les, des"},
        "sorting": {
            "prompt": "Range les étiquettes de la fiche.",
            "categories": [
                {"name": "Singulier", "members": ["un sapin", "la feuille"]},
                {"name": "Pluriel", "members": ["des lapins", "les choux"]},
            ],
        },
    }
    checked = validate_material(item(), raw, FICHE)
    material = checked.material
    assert [q.stem for q in material.questions] == ["Quel article va avec « maisons » ?"]
    assert material.true_statements == ["« Des plantes » est au pluriel."]
    assert material.cloze is None and material.flashcard is None and material.sorting is None
    reasons = [r.reason for r in checked.rejected]
    assert reasons.count(SUPPORT_REASON) == 5


def recit_item() -> KnowledgeItem:
    return KnowledgeItem(
        id="k1",
        type=KnowledgeType.FACT,
        label="Le panier du Petit Chaperon rouge",
        statement="Dans « Le Petit Chaperon rouge », elle apporte une galette et un pot de beurre.",
        importance=4,
        source_excerpt="avec une galette et un petit pot de beurre",
    )


def test_reading_question_shows_a_copied_passage() -> None:
    passage = "Le Petit Chaperon rouge part chez sa grand-mère avec une galette et un petit pot de beurre."
    raw = {
        "explanation": "Elle apporte une galette et un petit pot de beurre.",
        "questions": [
            mcq(
                "Dans ce passage, que porte le Petit Chaperon rouge ?",
                "une galette",
                ["une tarte", "du pain", "des fleurs"],
                passage,
            ),
            # Passage inventé : la question est écartée.
            mcq(
                "Qui rencontre-t-elle ?",
                "le loup",
                ["le chasseur", "un renard", "un ours"],
                "Elle rencontre un loup gris dans la forêt.",
            ),
        ],
        "open_questions": [
            {
                "level": 3,
                "prompt": "D'après ce texte, où va le Petit Chaperon rouge ?",
                "key_points": ["chez sa grand-mère"],
                "model_answer": "Elle va chez sa grand-mère.",
                "passage": passage,
            }
        ],
    }
    checked = validate_material(recit_item(), raw, RECIT)
    material = checked.material
    assert [q.passage for q in material.questions] == [passage]
    assert [r.reason for r in checked.rejected] == [PASSAGE_REASON]
    assert material.open_questions[0].passage == passage

    unit = KnowledgeUnit(item=recit_item(), material=material)
    payload = Mcq().build([unit], 1, random.Random(1)).payload
    assert payload["passage"] == passage
    open_payload = OpenQuestionActivity().build([unit], 1, random.Random(1)).payload
    assert open_payload["passage"] == passage
    assert any(
        "📖 « Le Petit Chaperon rouge" in line for block in material_blocks(material) for line in block.lines
    )


def test_without_passage_the_reading_question_is_refused() -> None:
    raw = {
        "explanation": "Elle apporte une galette.",
        "questions": [
            mcq("D'après le texte, que porte-t-elle ?", "une galette", ["une tarte", "du pain", "des fleurs"])
        ],
    }
    checked = validate_material(recit_item(), raw, RECIT)
    assert checked.material.questions == []
    assert [r.reason for r in checked.rejected] == [SUPPORT_REASON]
