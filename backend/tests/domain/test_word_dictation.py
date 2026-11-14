"""§5.99 : dictée à partir d'une liste de mots, fabriquée par le code."""

from app.domain.activities.base import ActivityCode
from app.domain.activities.registry import default_registry
from app.domain.knowledge import Grade, KnowledgeUnit, Subject
from app.domain.word_dictation import MAX_WORDS, WordEntry, dictation_lesson, parse_word_list
from app.domain.word_list import words_to_write

WRITING = {
    ActivityCode.WORD_FLASH,
    ActivityCode.SCRAMBLE,
    ActivityCode.DICTATION,
    ActivityCode.SENTENCE_DICTATION,
    ActivityCode.MCQ,
    ActivityCode.FILL_BLANK,
}


def test_one_word_per_line_with_an_optional_sentence() -> None:
    parsed = parse_word_list(
        "1. chaton : Le chaton dort sur le lit.\n- maison\n\n"
        "• École = Je vais à l'école.\naujourd’hui\nMaison"
    )
    assert parsed.problems == []
    assert parsed.entries == [
        WordEntry("chaton", "Le chaton dort sur le lit."),
        WordEntry("maison"),
        WordEntry("École", "Je vais à l'école."),
        WordEntry("aujourd’hui"),
    ]  # « Maison » en double est ignoré


def test_words_on_one_line_separated_by_commas() -> None:
    words = [e.word for e in parse_word_list("chaton, maison ; école").entries]
    assert words == ["chaton", "maison", "école"]


def test_each_refused_line_says_why() -> None:
    parsed = parse_word_list("chaton\n3 chats\nlapin : Le chat mange.\nmaison\nécole")
    assert parsed.problems == [
        "Ligne 2 : « 3 chats » n'est pas un mot (pas de chiffre).",
        "Ligne 3 : la phrase ne contient pas le mot « lapin ».",
    ]
    assert parse_word_list("chaton\nmaison").problems == ["Au moins 3 mots pour une dictée."]
    many = "\n".join(f"mot{'a' * i}" for i in range(MAX_WORDS + 1))
    assert parse_word_list(many).problems == [f"{MAX_WORDS} mots au plus pour une dictée."]


def test_the_lesson_has_only_writing_games_and_invents_nothing() -> None:
    lines = ["chaton : Le chaton dort sur le lit.", "maison", "école : Je vais à l'école."]
    built = dictation_lesson(parse_word_list("\n".join(lines)).entries, "Mots de la semaine", Grade.CE1)
    assert built.text == "\n".join(["Dictée : Mots de la semaine", *lines])
    lesson = built.analysis.lesson
    assert lesson is not None and lesson.subject is Subject.FRENCH and lesson.grade is Grade.CE1
    # Le code reconnaît lui-même une liste de mots (§5.68) : seulement des jeux d'écriture.
    assert words_to_write(built.analysis, built.text) == {"k1", "k2", "k3"}
    registry = default_registry()
    codes: dict[str, set[ActivityCode]] = {}
    for item in built.analysis.knowledge:
        validation = built.materials[item.id]
        assert validation.rejected == []
        unit = KnowledgeUnit(item=item, material=validation.material)
        codes[item.label] = {code for code, _ in registry.single_options(unit)}
        assert codes[item.label] and codes[item.label] <= WRITING
        assert item.source_excerpt in built.text
    assert ActivityCode.SENTENCE_DICTATION in codes["chaton"]  # avec sa phrase
    assert ActivityCode.SENTENCE_DICTATION not in codes["maison"]  # pas de phrase inventée
    assert {ActivityCode.DICTATION, ActivityCode.WORD_FLASH, ActivityCode.SCRAMBLE} <= codes["maison"]
    chaton = built.materials["k1"].material.spelling
    assert chaton is not None and chaton.sentence == "Le ___ dort sur le lit."


def test_unknown_grade_and_default_title() -> None:
    built = dictation_lesson([WordEntry("chaton"), WordEntry("maison"), WordEntry("école")], "  ", None)
    lesson = built.analysis.lesson
    assert lesson is not None and lesson.title == "Dictée" and lesson.grade_confidence == 0
