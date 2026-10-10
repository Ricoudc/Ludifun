"""§5.58 : la leçon prime. Les exercices, calculs et mots de la leçon d'abord ; ensuite seulement
des exercices inventés, dans les nombres de la leçon (vraies fiches de CE1 de la famille)."""

import random
import re
from datetime import UTC, datetime

from app.domain.activities.base import ActivityCode
from app.domain.activities.registry import ActivityRegistry
from app.domain.composer import SessionComposer, fingerprint
from app.domain.knowledge import (
    Grade,
    KnowledgeItem,
    KnowledgeMaterial,
    KnowledgeType,
    KnowledgeUnit,
    MaterialQuestion,
    Pair,
    Subject,
    Theme,
)
from app.domain.lesson_context import in_context
from app.domain.math_generator import lesson_ceiling, lesson_operations

C = ActivityCode
BANDE = (
    "Pour ajouter un nombre, je me déplace vers la droite sur la bande numérique : 10 + 4 = 14. "
    "Pour retrancher, je me déplace vers la gauche : 16 - 6 = 10."
)


def unit(
    label: str,
    statement: str,
    subject: Subject = Subject.MATH,
    theme: Theme | None = None,
    questions: list[MaterialQuestion] | None = None,
    pair: Pair | None = None,
) -> KnowledgeUnit:
    item = KnowledgeItem(
        id="k1",
        type=KnowledgeType.FACT,
        label=label,
        statement=statement,
        importance=5,
        source_excerpt=label,
        theme=theme,
    )
    material = KnowledgeMaterial(
        knowledge_id="k1", explanation="Relis la leçon.", questions=questions or [], pair=pair
    )
    return KnowledgeUnit(item=item, material=material)


def own(stem: str, answer: str, *wrong: str) -> MaterialQuestion:
    return MaterialQuestion(difficulty=1, stem=stem, answer=answer, distractors=list(wrong))


def bande() -> KnowledgeUnit:
    """La fiche « Ajouter ou retrancher un nombre » (Calc 3), avec deux de ses calculs."""
    questions = [own("9 + 4 = ?", "13", "12", "14", "5"), own("11 - 5 = ?", "6", "16", "5", "7")]
    base = unit("Ajouter sur la bande numérique", BANDE, theme=Theme.ADDITION, questions=questions)
    return in_context([base], Subject.MATH, Grade.CE1)[0]


def test_the_numbers_and_calculations_of_the_lesson_are_read() -> None:
    text = f"{BANDE} 9 + 4 = ? 13 11 − 5 Calc 3"
    assert lesson_ceiling(text) == 16
    assert lesson_operations(text) == [(10, "+", 4), (16, "−", 6), (9, "+", 4), (11, "−", 5)]
    assert lesson_ceiling("Les tables de 2 et de 5") is None  # pas de plafond sous 10


def test_invented_additions_stay_in_the_numbers_of_the_lesson() -> None:
    """Bande numérique de 1 à 21 : pas de « 33 − 22 » inventé au CE1."""
    generated = [q for q in bande().material.questions if q.generated]
    assert generated
    for question in generated:
        assert all(int(n) <= 16 for n in re.findall(r"\d+", question.stem)), question.stem


def test_number_line_moves_like_the_lesson(registry: ActivityRegistry) -> None:
    game = registry.get(C.NUMBER_LINE)
    lesson = bande()
    moves = {"10 + 4": 14, "16 − 6": 10, "9 + 4": 13, "11 − 5": 6}
    seen = set()
    for seed in range(40):
        activity = game.build([lesson], 1, random.Random(seed))
        labels = {label["index"]: int(label["text"]) for label in activity.payload["labels"]}
        start = labels[0]
        if activity.solution.get("from_lesson"):
            m = re.match(r"Pars de (\d+) et (avance|recule) de (\d+)\.", activity.payload["prompt"])
            assert m is not None
            a, b = int(m[1]), int(m[3])
            key = f"{a} {'+' if m[2] == 'avance' else '−'} {b}"
            assert start + activity.solution["index"] == moves[key]  # l'arrivée juste
            assert a in labels.values() and moves[key] not in labels.values()  # départ écrit
            seen.add(key)
        else:
            assert activity.solution["from_lesson"] is False
            assert max(labels.values()) <= 30  # inventé, dans les nombres de la leçon
    assert seen == set(moves)


def test_column_operation_poses_the_lesson_first(registry: ActivityRegistry) -> None:
    """Fiche « Calculer un complément » : 35 + 65 = 100 se pose ; les inventées ne dépassent pas 100."""
    game = registry.get(C.COLUMN_OP)
    base = unit("Additionner", "35 + 65 = 100 : je complète à la dizaine.", theme=Theme.ADDITION)
    lesson = in_context([base], Subject.MATH, Grade.CE1)[0]
    found = set()
    for seed in range(30):
        activity = game.build([lesson], 2, random.Random(seed))
        a, b = map(int, activity.payload["operands"])
        found.add(activity.solution["from_lesson"])
        if activity.solution["from_lesson"]:
            assert (a, b) == (35, 65)
        else:
            assert a <= 100 and b <= 100
    assert found == {True, False}
    # La bande numérique calcule en avançant : pas d'opération posée inventée pour elle.
    assert not game.accepts(bande())
    posed = unit("L'addition posée", "On pose l'addition en colonnes, avec la retenue.", theme=Theme.ADDITION)
    assert game.accepts(in_context([posed], Subject.MATH, Grade.CE1)[0])


def test_the_session_asks_the_lesson_questions_before_invented_ones(registry: ActivityRegistry) -> None:
    """Le QCM : d'abord les questions de la leçon ; une inventée seulement quand elles ont toutes
    été posées aux séances précédentes."""
    lesson = bande()
    composer = SessionComposer(registry, daily_game=False)
    rng = random.Random(1)
    first = composer._fresh(C.MCQ, lesson, 1, rng)
    assert first.solution["from_lesson"] is True
    asked = {
        fingerprint(composer._fresh(C.MCQ, lesson, 1, random.Random(seed)))
        for seed in range(40)
        if composer._fresh(C.MCQ, lesson, 1, random.Random(seed)).solution["from_lesson"]
    }
    assert len(asked) == 2  # les deux questions de la leçon
    composer.recent = frozenset(asked)
    later = composer._fresh(C.MCQ, lesson, 1, random.Random(2))
    assert later.solution["from_lesson"] is False and fingerprint(later) not in asked
    # La séance commence par un exercice de la leçon (QCM de la fiche ou déplacement sur la droite).
    for seed in range(6):
        plan = SessionComposer(registry, daily_game=False).compose(
            [lesson], {}, datetime(2026, 10, 10, tzinfo=UTC), seed
        )
        assert plan.items[0].activity.solution.get("from_lesson") is True


def test_synonyms_of_the_lesson_first(registry: ActivityRegistry) -> None:
    """Fiche « Les synonymes » : « une forêt et un bois sont deux mots synonymes », et une paire que
    la banque ne connaît pas (maison, demeure), sont toujours dans le jeu."""
    lesson = unit(
        "Les synonymes",
        "Une forêt et un bois sont deux mots synonymes.",
        subject=Subject.FRENCH,
        pair=Pair(left="maison", right="demeure"),
    ).model_copy(update={"subject": Subject.FRENCH, "grade": Grade.CE1})
    game = registry.get(C.SYNONYMS)
    for seed in range(15):
        activity = game.build([lesson], 1, random.Random(seed))
        words = {i["text"] for i in (*activity.payload["left"], *activity.payload["right"])}
        assert {"forêt", "bois", "maison", "demeure"} <= words


def test_word_family_of_the_lesson_first(registry: ActivityRegistry) -> None:
    """Fiche « Trouve un mot de la même famille » : la paire de la leçon passe d'abord, avec le
    piège de la banque s'il existe ; une famille inconnue de la banque est jouée sans piège."""
    game = registry.get(C.WORD_FAMILY)
    for pair, trap in (
        (Pair(left="ventilateur", right="vent"), "vendre"),
        (Pair(left="bijoutier", right="bijou"), None),
    ):
        lesson = unit(
            "Les mots de la même famille",
            "Trouve un mot de la même famille.",
            subject=Subject.FRENCH,
            pair=pair,
        ).model_copy(update={"subject": Subject.FRENCH, "grade": Grade.CE1})
        for seed in range(10):
            activity = game.build([lesson], 2, random.Random(seed))
            first = activity.payload["items"][0]
            assert first["text"].startswith(f"« {pair.left} »")
            assert activity.solution["expected"][first["id"]] == pair.right
            others = [c for c in first["choices"] if c != pair.right]
            assert (trap in others) if trap else all(not c.startswith("bijo") for c in others)
