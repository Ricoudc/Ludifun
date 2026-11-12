"""Fiche d'exercices photographiée (ordre alphabétique) : l'IA ne doit pas recopier les consignes.

Cas réel : sept questions « Écris la lettre qui précède selon l'ordre alphabétique. » avec
sept réponses différentes (a, d, i…) ; l'enfant ne peut pas savoir de quelle lettre on parle.
"""

from app.domain.knowledge import KnowledgeItem, KnowledgeType
from app.domain.validation import validate_material

CONSIGNE = "Écris la lettre qui précède selon l'ordre alphabétique."


def item(label: str = "La lettre qui précède") -> KnowledgeItem:
    return KnowledgeItem(
        id="k1",
        type=KnowledgeType.RULE,
        label=label,
        statement="La lettre qui précède est celle qui vient juste avant dans l'alphabet.",
        importance=5,
        attributes={"statement": "La lettre qui précède vient juste avant.", "example": "avant b : a"},
        source_excerpt=CONSIGNE,
    )


def mcq(stem: str, answer: str, distractors: list[str]) -> dict[str, object]:
    return {"stem": stem, "answer": answer, "distractors": distractors, "difficulty": 1}


def test_copied_instructions_are_refused() -> None:
    raw = {
        "explanation": "On compte une lettre en arrière.",
        "questions": [
            mcq(CONSIGNE, "a", ["b", "c", "d"]),
            mcq(CONSIGNE, "d", ["c", "e", "f"]),
            mcq(CONSIGNE, "i", ["h", "j", "k"]),
            mcq("Quelle lettre vient juste avant b dans l'alphabet ?", "a", ["c", "d", "e"]),
        ],
        "true_statements": [
            "Écrire la lettre qui précède selon l'ordre alphabétique.",
            "La lettre avant e est d.",
        ],
        "false_statements": ["Écrire la lettre qui suit selon l'ordre alphabétique."],
        "cloze": {"text": f"{CONSIGNE} ___", "answers": ["a", "d", "i", "n", "p", "t", "y"]},
        "spelling": {"word": "lettre"},
        "open_questions": [
            {
                "level": 3,
                "prompt": CONSIGNE,
                "key_points": ["a"],
                "model_answer": f"{CONSIGNE} a",
            }
        ],
    }
    checked = validate_material(item(), raw)
    material = checked.material
    # Seule la question complète reste ; les trois consignes recopiées sont refusées.
    assert [q.stem for q in material.questions] == ["Quelle lettre vient juste avant b dans l'alphabet ?"]
    assert material.true_statements == ["La lettre avant e est d."]
    assert material.false_statements == []
    assert material.cloze is None
    assert material.spelling is None
    assert material.open_questions == []
    reasons = {r.reason for r in checked.rejected}
    assert "la même question a plusieurs réponses : il manque la donnée (laquelle ?)" in reasons
    assert "c'est une consigne d'exercice, pas une affirmation vraie ou fausse" in reasons
    assert "la réponse attendue recopie la question" in reasons


def test_a_repeated_question_with_the_same_answer_is_kept_once() -> None:
    question = mcq("Quelle lettre vient juste après c ?", "d", ["b", "e", "f"])
    checked = validate_material(item(), {"explanation": "x", "questions": [question, question]})
    assert len(checked.material.questions) == 1
    assert [r.reason for r in checked.rejected] == ["question en double"]
