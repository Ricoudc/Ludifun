"""Listes de mots à savoir écrire : « Mot éclair » et « Lettres mélangées ».

- le mot vient de la notion, écrit pareil (accents compris) ; sinon il est refusé ;
- l'orthographe est notée strictement (accents), sans compter majuscules et apostrophes ;
- une faute de peu est une imprécision, pour le parent comme pour le moteur.
"""

import random

from app.domain.activities.base import ActivityCode
from app.domain.activities.registry import ActivityRegistry
from app.domain.errors import ErrorType
from app.domain.instructions import instruction
from app.domain.knowledge import KnowledgeItem, KnowledgeType, KnowledgeUnit
from app.domain.material_view import material_blocks
from app.domain.mistakes import describe
from app.domain.simulated_pupil import respond
from app.domain.validation import validate_material


def word_item(word: str = "hôpital", kid: str = "k1") -> KnowledgeItem:
    return KnowledgeItem(
        id=kid,
        type=KnowledgeType.TERM,
        label=word,
        statement=f"Le mot « {word} » est dans la liste de la semaine.",
        importance=4,
        attributes={"definition": f"Le mot {word}"},
        source_excerpt=word,
    )


def spelling_unit(
    word: str = "hôpital", sentence: str | None = "Le docteur travaille à l'___."
) -> KnowledgeUnit:
    item = word_item(word)
    validated = validate_material(
        item, {"explanation": f"On écrit « {word} ».", "spelling": {"word": word, "sentence": sentence}}
    )
    assert validated.rejected == [], validated.rejected
    return KnowledgeUnit(item=item, material=validated.material)


def test_the_word_must_be_written_as_in_the_lesson() -> None:
    item = word_item("hôpital")
    wrong = validate_material(item, {"explanation": "x", "spelling": {"word": "hopital"}})
    assert wrong.material.spelling is None
    assert [r.element for r in wrong.rejected] == ["spelling"]
    # Une phrase d'aide qui donne le mot, ou sans « ___ », est retirée ; le mot reste.
    for sentence in ("Je vais à l'hôpital.", "Je vais au docteur."):
        kept = validate_material(
            item, {"explanation": "x", "spelling": {"word": "hôpital", "sentence": sentence}}
        )
        assert kept.material.spelling is not None and kept.material.spelling.sentence is None


def test_word_flash(registry: ActivityRegistry) -> None:
    unit = spelling_unit()
    game = registry.get(ActivityCode.WORD_FLASH)
    easy, hard = game.build([unit], 2, random.Random(1)), game.build([unit], 3, random.Random(1))
    assert easy.payload["word"] == "hôpital" and easy.payload["show_ms"] > hard.payload["show_ms"]
    assert easy.payload["sentence"] == "Le docteur travaille à l'___."
    assert game.grade(easy, {"text": " Hôpital "}).score == 1
    missing_accent = game.grade(easy, {"text": "hopital"})
    assert missing_accent.score == 0 and missing_accent.errors == {"k1": ErrorType.IMPRECISION}
    assert missing_accent.correct_answer == "hôpital"
    assert game.grade(easy, respond(easy, lambda _: True)).score == 1
    assert game.grade(easy, respond(easy, lambda _: False)).score == 0


def test_scramble(registry: ActivityRegistry) -> None:
    unit = spelling_unit("chevaux", None)
    game = registry.get(ActivityCode.SCRAMBLE)
    for seed in range(20):
        activity = game.build([unit], 1, random.Random(seed))
        letters = [letter["text"] for letter in activity.payload["letters"]]
        assert sorted(letters) == sorted("chevaux") and "".join(letters) != "chevaux"
        assert game.grade(activity, respond(activity, lambda _: True)).score == 1
        assert game.grade(activity, respond(activity, lambda _: False)).score == 0
    # Trop court, trop long, plusieurs mots : pas de lettres mélangées (le mot éclair reste).
    for word in ("un", "anticonstitutionnellement", "tout à coup"):
        assert not game.accepts(spelling_unit(word, None)), word
        assert registry.get(ActivityCode.WORD_FLASH).accepts(spelling_unit(word, None))


def test_the_parent_sees_the_word_and_the_mistake(registry: ActivityRegistry) -> None:
    unit = spelling_unit()
    blocks = material_blocks(unit.material)
    spelling = next(b for b in blocks if b.title.startswith("✍️"))
    assert spelling.lines[0] == "hôpital" and spelling.game == ActivityCode.WORD_FLASH
    activity = registry.get(ActivityCode.WORD_FLASH).build([unit], 2, random.Random(1))
    mistake = describe(registry, activity, {"text": "opital"})
    assert mistake is not None and mistake.given == "opital" and mistake.expected == "hôpital"
    for code in (ActivityCode.WORD_FLASH, ActivityCode.SCRAMBLE):
        assert "écri" in str(instruction(code, "CP")).lower() or "mot" in str(instruction(code, "CP"))


def test_a_word_list_gets_writing_games_in_the_session(registry: ActivityRegistry) -> None:
    from app.domain.composer import SessionComposer
    from tests.domain.test_composer import NOW

    units = [spelling_unit(w, None) for w in ("chevaux", "hôpital", "toujours", "beaucoup")]
    units = [
        KnowledgeUnit(
            item=u.item.model_copy(update={"id": f"k{i}"}),
            material=u.material.model_copy(update={"knowledge_id": f"k{i}"}),
        )
        for i, u in enumerate(units, start=1)
    ]
    types = {
        a.activity.type
        for seed in range(5)
        for a in SessionComposer(registry).compose(units, {}, NOW, seed).items
    }
    assert {ActivityCode.WORD_FLASH, ActivityCode.SCRAMBLE} <= types


def test_dictation(registry: ActivityRegistry) -> None:
    """Dictée : le mot est prononcé par le téléphone, jamais affiché ; la phrase lue le contient."""
    unit = spelling_unit()
    game = registry.get(ActivityCode.DICTATION)
    activity = game.build([unit], 3, random.Random(1))
    assert activity.payload["word"] == "hôpital"
    assert activity.payload["sentence"] == "Le docteur travaille à l'___."
    assert activity.payload["spoken_sentence"] == "Le docteur travaille à l'hôpital."
    assert game.grade(activity, {"text": "hôpital"}).score == 1
    assert game.grade(activity, {"text": "hopitale"}).score == 0
    assert (
        game.build([spelling_unit("chevaux", None)], 3, random.Random(1)).payload["spoken_sentence"] is None
    )
    mistake = describe(registry, activity, {"text": "opital"})
    assert mistake is not None and mistake.given == "opital"
