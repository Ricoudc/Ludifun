"""Listes de mots à savoir écrire (§5.68, règles 1.15.0) : le but est que l'enfant sache les écrire.

- le code reconnaît une liste de mots et reprend de la leçon le mot que l'IA a oublié ;
- un mot à savoir écrire ne se travaille qu'avec des jeux d'écriture (en français) ;
- de bout en bout : une IA qui « oublie » les mots donne quand même une séance de jeux d'écriture.
"""

import copy
from datetime import UTC, datetime
from typing import Any

import pytest

from app.ai.ocr.vision_llm import VisionLLMOcr
from app.ai.providers.fake import FakeProvider, LessonScript
from app.domain.activities.base import ActivityCode, writing_only
from app.domain.activities.registry import ActivityRegistry, default_registry
from app.domain.composer import SessionComposer
from app.domain.decisions import describe
from app.domain.knowledge import Grade, KnowledgeUnit, LessonAnalysis, Subject
from app.domain.rules import RULES
from app.domain.validation import validate_analysis, validate_material
from app.domain.word_list import with_spelling, words_to_write
from app.services.lesson_pipeline import LessonPipeline

WORDS = ["hôpital", "chevaux", "aujourd'hui", "toujours", "beaucoup"]
TEXT = "Mots de la semaine à savoir écrire : " + ", ".join(WORDS) + "."
WRITING = {ActivityCode(code) for code in RULES.spelling.writing_games}


def raw_analysis(
    words: list[str] = WORDS,
    title: str = "Les mots de la semaine",
    subject: str = "french",
    skill: str = "Écrire sans erreur les mots de la liste",
    objective: str = "Connaître les mots de la semaine",
) -> dict[str, Any]:
    knowledge = [
        {
            "id": f"k{i}",
            "type": "term",
            "label": word,
            "statement": f"Il faut savoir écrire le mot « {word} ».",
            "importance": 4,
            "attributes": {"definition": f"Le mot {word}"},
            "source_excerpt": word,
            "relations": [],
        }
        for i, word in enumerate(words, 1)
    ]
    return {
        "schema_version": "2.0",
        "is_lesson": True,
        "lesson": {
            "subject": subject,
            "grade": "CE1",
            "grade_confidence": 0.9,
            "title": title,
            "objective": objective,
            "summary": "Une liste de mots.",
        },
        "skills": [
            {
                "id": "s1",
                "label": skill,
                "verb": "recall",
                "importance": 5,
                "knowledge_ids": [k["id"] for k in knowledge],
                "source_excerpt": "Mots de la semaine",
            }
        ],
        "knowledge": knowledge,
        "warnings": [],
    }


def analysis(**kwargs: Any) -> LessonAnalysis:
    validated = validate_analysis(raw_analysis(**kwargs), TEXT)
    assert validated.analysis is not None, validated.rejected
    return validated.analysis


def test_a_list_of_words_is_recognised() -> None:
    assert words_to_write(analysis(), TEXT) == {"k1", "k2", "k3", "k4", "k5"}
    # Reconnue par la compétence seule (titre neutre), ou par le titre seul (compétence neutre).
    assert len(words_to_write(analysis(title="Semaine 12"), TEXT)) == 5
    assert len(words_to_write(analysis(skill="Connaître les mots de la liste"), TEXT)) == 5


def test_what_is_not_a_list_of_words_to_write() -> None:
    neutral = {"title": "Semaine 12", "skill": "Connaître les mots", "objective": "Les connaître"}
    assert words_to_write(analysis(**neutral), TEXT) == set()  # rien ne parle d'écrire
    assert words_to_write(analysis(subject="history"), TEXT) == set()  # vocabulaire d'histoire
    assert words_to_write(analysis(words=WORDS[:2]), TEXT) == set()  # deux mots : pas une liste


def test_the_missing_word_is_taken_from_the_lesson() -> None:
    lesson = analysis()
    item = lesson.knowledge[0]
    alone = with_spelling(item, None, TEXT)  # l'IA n'a rien donné pour ce mot
    assert alone.material.spelling is not None and alone.material.spelling.word == "hôpital"
    from_ai = validate_material(
        item,
        {
            "explanation": "On écrit hôpital avec un accent.",
            "true_statements": ["Le mot hôpital a un accent."],
        },
        TEXT,
    )
    completed = with_spelling(item, from_ai, TEXT)  # ce que l'IA a donné est gardé
    assert completed.material.spelling is not None and completed.material.true_statements
    assert with_spelling(item, completed, TEXT) is completed  # déjà là : rien ne change


def unit(subject: Subject | None = Subject.FRENCH) -> KnowledgeUnit:
    item = analysis().knowledge[0]
    material = validate_material(
        item,
        {
            "explanation": "On écrit hôpital avec un accent circonflexe.",
            "true_statements": ["Le mot hôpital a un accent circonflexe sur le o."],
            "false_statements": ["Le mot hôpital a un accent aigu sur le o."],
            "spelling": {"word": "hôpital", "sentence": "Le docteur travaille à l'___."},
        },
        TEXT,
    ).material
    return KnowledgeUnit(item=item, material=material, subject=subject, grade=Grade.CE1)


def test_only_writing_games_for_a_word_to_write(registry: ActivityRegistry) -> None:
    word = unit()
    assert writing_only(word)
    assert registry.formats_for(word) <= WRITING
    assert ActivityCode.TRUE_FALSE not in registry.formats_for(word)  # il a pourtant des affirmations
    without_word = word.model_copy(update={"material": word.material.model_copy(update={"spelling": None})})
    assert ActivityCode.TRUE_FALSE in registry.formats_for(without_word)
    # Vocabulaire d'histoire : le sens compte aussi, pas de restriction.
    history = word.model_copy(update={"subject": Subject.HISTORY})
    assert not writing_only(history) and ActivityCode.TRUE_FALSE in registry.formats_for(history)


def material_without_words(words: list[str]) -> dict[str, dict[str, Any]]:
    """Ce que rend une IA qui oublie le mot à savoir écrire : une explication, sans le mot."""
    return {
        f"k{i}": {"knowledge_id": f"k{i}", "explanation": f"Il faut savoir écrire le mot {word}."}
        for i, word in enumerate(words, 1)
    }


@pytest.mark.parametrize("forgotten", [True, False], ids=["IA qui oublie", "IA qui donne le mot"])
async def test_end_to_end_a_list_of_words_gives_writing_games(forgotten: bool) -> None:
    material = material_without_words(WORDS)
    if not forgotten:
        for i, word in enumerate(WORDS, 1):
            material[f"k{i}"]["spelling"] = {"word": word, "sentence": None}
    llm = FakeProvider(LessonScript(TEXT, raw_analysis(), copy.deepcopy(material)))
    pipeline = LessonPipeline(VisionLLMOcr(llm), llm, default_registry())
    result = await pipeline.run((), TEXT)
    assert result.ready and len(result.units) == 5
    assert all(u.material.spelling is not None for u in result.units)
    units = [u.model_copy(update={"subject": Subject.FRENCH, "grade": Grade.CE1}) for u in result.units]
    plan = SessionComposer(default_registry(), daily_game=False).compose(
        units, {}, datetime(2026, 11, 7, tzinfo=UTC), seed=4
    )
    games = [p.activity.type for p in plan.items]
    assert games and set(games) <= WRITING  # ni vrai/faux, ni définitions à relier
    assert ActivityCode.SCRAMBLE in games and ActivityCode.WORD_FLASH in games
    assert plan.items[0].block.value == "warmup"  # l'échauffement : lettres mélangées
    assert all("seulement des jeux où l'on écrit le mot" in (describe(p.reason) or "") for p in plan.items)
    # Une seule demande de matériel : le mot oublié ne coûte pas de relance à l'IA (quota en ligne).
    assert [stage for stage, _ in llm.calls].count("material") == 1
