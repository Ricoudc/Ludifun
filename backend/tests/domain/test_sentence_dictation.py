"""Dictée de phrases (§5.64) : le téléphone lit une phrase qui emploie un mot de la liste ;
l'enfant l'écrit.

- la phrase vient de la leçon d'abord, sinon de la phrase d'aide du matériel ;
- sa longueur suit la classe ; chiffres et guillemets ne sont jamais dictés ;
- correction mot à mot alignée : un mot oublié ne fait pas compter faux les suivants ;
- la maîtrise de la notion ne regarde que le mot de la liste.
"""

import random

import pytest

from app.domain.activities.base import ActivityCode
from app.domain.activities.registry import ActivityRegistry
from app.domain.activities.sentence_dictation import align, sentences_of, words_of
from app.domain.errors import ErrorType
from app.domain.instructions import instruction
from app.domain.knowledge import Grade, KnowledgeItem, KnowledgeType, KnowledgeUnit, Subject
from app.domain.mistakes import describe, question_of
from app.domain.simulated_pupil import respond
from app.domain.validation import validate_material


def unit(
    word: str = "hôpital",
    sentence: str | None = "Le docteur travaille à l'___.",
    statement: str = "Le mot « hôpital » est dans la liste de la semaine.",
    true_statements: tuple[str, ...] = (),
    grade: Grade | None = Grade.CE1,
    subject: Subject | None = Subject.FRENCH,
) -> KnowledgeUnit:
    item = KnowledgeItem(
        id="k1",
        type=KnowledgeType.TERM,
        label=word,
        statement=statement,
        importance=4,
        attributes={"definition": f"Le mot {word}"},
        source_excerpt=word,
    )
    validated = validate_material(
        item,
        {
            "explanation": f"On écrit « {word} ».",
            "spelling": {"word": word, "sentence": sentence},
            "true_statements": list(true_statements),
        },
    )
    assert validated.material.spelling is not None, validated.rejected
    return KnowledgeUnit(item=item, material=validated.material, grade=grade, subject=subject)


def build(registry: ActivityRegistry, u: KnowledgeUnit, seed: int = 1):  # type: ignore[no-untyped-def]
    return registry.get(ActivityCode.SENTENCE_DICTATION).build([u], 3, random.Random(seed))


def test_the_helper_sentence_is_dictated_with_the_word(registry: ActivityRegistry) -> None:
    activity = build(registry, unit())
    assert activity.payload["sentence"] == "Le docteur travaille à l'hôpital."
    assert activity.payload["word_count"] == 6  # « l' » et « hôpital » comptent pour deux
    assert " ".join(activity.payload["chunks"]) == activity.payload["sentence"]
    assert 2 <= len(activity.payload["chunks"]) <= 3
    assert activity.solution["from_lesson"] is False
    assert "word" not in activity.payload  # rien ne montre le mot à l'écran


def test_a_lesson_sentence_comes_first(registry: ActivityRegistry) -> None:
    u = unit(statement="On soigne les malades à l'hôpital.")
    for seed in range(10):
        activity = build(registry, u, seed)
        assert activity.payload["sentence"] == "On soigne les malades à l'hôpital."
        assert activity.solution["from_lesson"] is True


def test_what_is_never_dictated() -> None:
    # Guillemets (phrase sur la liste elle-même), chiffres, mot absent, trop long pour la classe.
    assert sentences_of(unit(sentence=None)) == ([], [])
    assert sentences_of(unit(sentence=None, true_statements=("Il y a 3 lits à l'hôpital.",))) == ([], [])
    assert sentences_of(unit(sentence=None, true_statements=("Le docteur soigne les malades.",))) == ([], [])
    long = "Le grand docteur de la ville travaille tous les jours à l'hôpital."
    assert sentences_of(unit(sentence=None, true_statements=(long,), grade=Grade.CE1)) == ([], [])
    assert sentences_of(unit(sentence=None, true_statements=(long,), grade=Grade.CM1)) == ([long], [])
    assert sentences_of(unit(sentence=None, true_statements=(long,), grade=None)) == ([long], [])


def test_not_in_math_nor_english(registry: ActivityRegistry) -> None:
    game = registry.get(ActivityCode.SENTENCE_DICTATION)
    assert game.accepts(unit())
    assert game.accepts(unit(subject=Subject.HISTORY))
    assert not game.accepts(unit(subject=Subject.MATH))
    assert not game.accepts(unit(subject=Subject.ENGLISH))


def test_words_ignore_punctuation_and_split_elisions() -> None:
    expected = ["Le", "docteur", "travaille", "à", "l'", "hôpital"]
    assert words_of("Le docteur travaille à l'hôpital.") == expected
    assert words_of("Le docteur, travaille à l’ hôpital") == expected


def test_a_forgotten_word_does_not_shift_the_others() -> None:
    pairs, extra = align(["le", "petit", "chat", "dort"], ["le", "chat", "dort", "bien"])
    assert pairs == [("le", "le"), ("petit", None), ("chat", "chat"), ("dort", "dort")]
    assert extra == ["bien"]
    pairs, extra = align(["le", "chat"], ["le", "chas"])
    assert pairs == [("le", "le"), ("chat", "chas")] and extra == []


def test_grading(registry: ActivityRegistry) -> None:
    game = registry.get(ActivityCode.SENTENCE_DICTATION)
    activity = build(registry, unit())
    # Majuscules, ponctuation et apostrophe typographique ne comptent pas.
    perfect = game.grade(activity, {"text": "le docteur travaille à l’hôpital"})
    assert perfect.score == 1 and perfect.evidence == {"k1": 1.0} and perfect.details == []
    # Un autre mot raté : l'enfant a presque tout, la notion (le mot de la liste) est sue.
    other = game.grade(activity, {"text": "Le doctor travaille à l'hôpital."})
    assert other.result == "partial" and other.score == pytest.approx(5 / 6)
    assert other.evidence == {"k1": 1.0} and other.errors == {}
    assert other.details == [{"text": "doctor", "expected": "docteur", "correct": False}]
    assert other.correct_answer == "Le docteur travaille à l'hôpital."
    # Le mot de la liste sans accent : la notion n'est pas sue, faute de peu.
    accent = game.grade(activity, {"text": "Le docteur travaille à l'hopital."})
    assert accent.evidence == {"k1": 0.0} and accent.errors == {"k1": ErrorType.IMPRECISION}
    # Le mot de la liste oublié, un mot en trop.
    forgotten = game.grade(activity, {"text": "Le docteur travaille bien à l'"})
    assert forgotten.evidence == {"k1": 0.0} and forgotten.score < 1
    assert {"text": "mot oublié", "expected": "hôpital", "correct": False} in forgotten.details
    assert {"text": "bien (mot en trop)", "correct": False} in forgotten.details
    # Tout juste mais un mot en plus : pas parfait.
    assert game.grade(activity, {"text": "Le docteur travaille à l'hôpital aussi."}).score < 1


def test_simulated_pupil_and_parent_view(registry: ActivityRegistry) -> None:
    game = registry.get(ActivityCode.SENTENCE_DICTATION)
    activity = build(registry, unit())
    assert game.grade(activity, respond(activity, lambda _: True)).score == 1
    wrong = respond(activity, lambda _: False)
    assert wrong == {"text": "Le docteur travaille à l'hôpita."}
    assert game.grade(activity, wrong).evidence == {"k1": 0.0}
    mistake = describe(registry, activity, wrong)
    assert mistake is not None
    assert mistake.given == "Le docteur travaille à l'hôpita."
    assert mistake.expected == "Le docteur travaille à l'hôpital."
    assert "phrase" in question_of(activity) and "hôpital" not in question_of(activity)
    assert instruction(ActivityCode.SENTENCE_DICTATION, Grade.CP)


def test_short_sentences_for_the_youngest(registry: ActivityRegistry) -> None:
    # Au CP, 6 mots au plus : « Le docteur travaille vite à l'hôpital. » passe, un mot de plus non.
    assert sentences_of(unit(sentence="Le docteur travaille vite à l'___.", grade=Grade.CP))[1]
    assert not sentences_of(unit(sentence="Le grand docteur travaille vite à l'___.", grade=Grade.CP))[1]
