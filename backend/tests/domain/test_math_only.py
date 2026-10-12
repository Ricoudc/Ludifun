"""Une leçon de maths ne fait réviser que les maths (règles 1.11.0) : pas de jeu d'orthographe,
pas de phrase à remettre dans l'ordre (les calculs, oui), pas de question d'orthographe."""

import random

from app.domain.activities.base import ActivityCode
from app.domain.activities.registry import ActivityRegistry
from app.domain.knowledge import KnowledgeMaterial, MaterialQuestion, Subject
from app.domain.math_generator import math_only
from tests.domain.test_spelling_games import spelling_unit

SPELLING_GAMES = {ActivityCode.WORD_FLASH, ActivityCode.SCRAMBLE, ActivityCode.DICTATION}


def test_no_spelling_game_in_a_math_lesson(registry: ActivityRegistry) -> None:
    word = spelling_unit("numérateur", "Le ___ est le nombre du haut.")
    assert registry.formats_for(word) >= SPELLING_GAMES  # leçon de français : les jeux de mots
    math = word.model_copy(update={"subject": Subject.MATH})
    assert not SPELLING_GAMES & registry.formats_for(math)
    assert not SPELLING_GAMES & {code for code, _ in registry.single_options(math)}


def test_a_math_lesson_unjumbles_calculations_only(registry: ActivityRegistry) -> None:
    unit = spelling_unit("numérateur", "Le ___ est le nombre du haut.")
    material = unit.material.model_copy(
        update={"true_statements": ["Le numérateur est le nombre du haut", "3 × 4 = 12"]}
    )
    french = unit.model_copy(update={"material": material})
    math = french.model_copy(update={"subject": Subject.MATH})
    game = registry.get(ActivityCode.UNJUMBLE)
    sentences = {game.build([math], 2, random.Random(i)).solution["sentence"] for i in range(10)}
    assert sentences == {"3 × 4 = 12"}
    assert "Le numérateur est le nombre du haut" in {
        game.build([french], 2, random.Random(i)).solution["sentence"] for i in range(20)
    }
    only_words = math.model_copy(
        update={"material": material.model_copy(update={"true_statements": ["Le numérateur est en haut"]})}
    )
    assert not game.accepts(only_words)


def test_spelling_questions_are_removed_from_math_material() -> None:
    def question(stem: str) -> MaterialQuestion:
        return MaterialQuestion(difficulty=1, stem=stem, answer="a", distractors=["b", "c", "d"])

    material = KnowledgeMaterial(
        knowledge_id="k1",
        explanation="Le numérateur est en haut.",
        questions=[
            question("Quelle est la bonne orthographe ?"),
            question("Comment s'écrit le mot « dénominateur » ?"),
            question("Dans 3/4, quel est le numérateur ?"),
        ],
    )
    kept = math_only(material)
    assert [q.stem for q in kept.questions] == ["Dans 3/4, quel est le numérateur ?"]
    assert math_only(kept) is kept
