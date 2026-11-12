"""Étape 14 (domaine) : aide progressive, questions ouvertes, types d'erreurs."""

import random
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.activities.base import ActivityCode
from app.domain.activities.open_question import OpenEvaluation, OpenQuestionActivity, point_found
from app.domain.activities.registry import ActivityRegistry
from app.domain.composer import SessionComposer
from app.domain.errors import (
    ErrorOccurrence,
    ErrorType,
    recurring_errors,
    with_speed,
    written_answer_error,
)
from app.domain.help import ExternalHelp, HelpKind, next_help, result_with_help, reveals
from app.domain.knowledge import HelpLadder, KnowledgeUnit, OpenQuestion, WorkedExample
from app.domain.mastery import Mastery
from app.domain.scoring import evidences_from, validated_levels
from app.domain.understanding import cognitive_level, required_levels
from tests.domain.conftest import ReferenceLesson

NOW = datetime(2026, 9, 24, 17, 0, tzinfo=UTC)
LADDER = HelpLadder(
    hint="Regarde le nombre du bas.",
    reminder="Même dénominateur : on compare les numérateurs.",
    example=WorkedExample(question="3/5 ou 4/5 ?", answer="4/5", why="4 est plus grand que 3."),
    steps=["Vérifie que les dénominateurs sont égaux.", "Compare les numérateurs."],
)
EXPLAIN = OpenQuestion(
    level=4,
    prompt="Explique pourquoi 5/8 est plus grand que 3/8.",
    key_points=["même dénominateur", "on compare les numérateurs", "5 est plus grand que 3"],
    model_answer="Les deux fractions ont le même dénominateur, donc on compare les numérateurs : 5 > 3.",
)


def with_material(unit: KnowledgeUnit, **changes: object) -> KnowledgeUnit:
    return unit.model_copy(update={"material": unit.material.model_copy(update=changes)})


# --------------------------------------------------------------------------- #
# Aide progressive
# --------------------------------------------------------------------------- #


def test_help_climbs_five_levels_and_reveals_the_answer_last(
    math: ReferenceLesson, registry: ActivityRegistry
) -> None:
    unit = with_material(math.unit("k4"), help=LADDER)
    activity = registry.get(ActivityCode.MCQ).build([unit], 1, random.Random(1))
    answer = activity.solution["display"]
    steps, level = [], 0
    while level < 5:
        step = next_help(unit, activity, level)
        steps.append(step)
        level = step.level
    assert [s.kind for s in steps] == [
        HelpKind.HINT,
        HelpKind.REMINDER,
        HelpKind.EXAMPLE,
        HelpKind.STEPS,
        HelpKind.ANSWER,
    ]
    assert all(answer not in " ".join([s.text, *s.lines]) for s in steps[:-1])
    assert steps[-1].text == answer and steps[-1].last
    assert steps[2].lines[0] == "→ 4/5"


def test_help_that_would_give_the_answer_away_is_skipped(
    history: ReferenceLesson, registry: ActivityRegistry
) -> None:
    # Leçon analysée avant l'étape 14 : pas d'aides, mais une astuce qui contient « 1789 ».
    unit = history.unit("k1")
    activity = registry.get(ActivityCode.FILL_BLANK).build([unit], 2, random.Random(1))
    assert "1789" in (unit.material.tip or "")
    first = next_help(unit, activity, 0)
    # L'astuce dévoilerait la réponse ; une date n'a pas de rappel de règle : on passe à la réponse.
    assert first.kind is HelpKind.ANSWER
    assert first.text == "1789"


def test_help_falls_back_on_a_generic_hint(math: ReferenceLesson, registry: ActivityRegistry) -> None:
    unit = with_material(math.unit("k4"), tip=None, help=None)
    activity = registry.get(ActivityCode.MCQ).build([unit], 1, random.Random(1))
    assert next_help(unit, activity, 0).text.startswith("Relis bien la question")
    # Une règle se rappelle sans donner la réponse de l'exercice.
    assert next_help(unit, activity, 1).text == unit.item.statement


def test_sourced_help_stands_in_for_a_missing_example(
    math: ReferenceLesson, registry: ActivityRegistry
) -> None:
    """Étape 24b : sans exemple dans la leçon, l'explication d'un site éducatif, marquée comme
    apport externe ; jamais à la place d'un exemple de la leçon, jamais si elle dévoile la réponse."""
    external = ExternalHelp("Quand le bas est pareil, le plus grand haut gagne.", "fr.vikidia.org")
    no_example = with_material(math.unit("k4"), help=LADDER.model_copy(update={"example": None}))
    activity = registry.get(ActivityCode.MCQ).build([no_example], 1, random.Random(1))
    step = next_help(no_example, activity, 2, external)
    assert (step.level, step.kind, step.text) == (3, HelpKind.SOURCED, external.text)
    assert step.title == "📚 Expliqué autrement" and step.lines == ["📚 En plus de ta leçon — fr.vikidia.org"]
    assert next_help(no_example, activity, 2).kind is HelpKind.STEPS  # sans source : on passe
    with_example = with_material(math.unit("k4"), help=LADDER)
    assert next_help(with_example, activity, 2, external).kind is HelpKind.EXAMPLE
    telling = ExternalHelp(f"La réponse est {activity.solution['display']}.", "fr.vikidia.org")
    assert next_help(no_example, activity, 2, telling).kind is HelpKind.STEPS


def test_help_reduces_proof_of_mastery_but_not_the_score(
    math: ReferenceLesson, registry: ActivityRegistry
) -> None:
    unit = math.unit("k2")
    activity = registry.get(ActivityCode.FILL_BLANK).build([unit], 2, random.Random(1))
    grade = registry.for_activity(activity).grade(activity, {"text": activity.solution["answers"][0]})
    assert grade.score == 1
    results = {h: evidences_from(activity, grade, registry, help_level=h)[0].result for h in range(6)}
    assert results == {0: 1.0, 1: 1.0, 2: 1.0, 3: 0.75, 4: 0.5, 5: 0.0}
    assert result_with_help(1.0, 9) == 0.0
    # Après l'exemple, une réponse juste ne valide plus le niveau « se rappeler ».
    assert validated_levels(evidences_from(activity, grade, registry, help_level=2)) == {"k2": {2}}
    assert validated_levels(evidences_from(activity, grade, registry, help_level=3)) == {}


# --------------------------------------------------------------------------- #
# Questions ouvertes
# --------------------------------------------------------------------------- #


def test_open_question_levels_and_requirements(math: ReferenceLesson, registry: ActivityRegistry) -> None:
    assert [cognitive_level(ActivityCode.OPEN_QUESTION, d) for d in (1, 2, 3)] == [3, 4, 5]
    unit = with_material(math.unit("k4"), open_questions=[EXPLAIN])
    assert (ActivityCode.OPEN_QUESTION, 2) in registry.single_options(unit)
    assert required_levels(unit, registry) == {1, 2, 3}  # expliquer approfondit, sans être exigé


def test_open_question_graded_by_key_points_without_the_evaluator(
    math: ReferenceLesson, registry: ActivityRegistry
) -> None:
    unit = with_material(math.unit("k4"), open_questions=[EXPLAIN])
    activity = registry.get(ActivityCode.OPEN_QUESTION).build([unit], 2, random.Random(1))
    assert activity.payload == {"prompt": EXPLAIN.prompt, "max_length": 600}
    open_question = registry.get(ActivityCode.OPEN_QUESTION)

    full = open_question.grade(
        activity,
        {"text": "Même dénominateur, alors on compare les numérateurs : 5 est plus grand que 3."},
    )
    assert full.score == 1 and full.errors == {}
    assert [d["found"] for d in full.details] == [True, True, True]

    partial = open_question.grade(activity, {"text": "Parce que 5 est plus grand que 3."})
    assert partial.score == 0.33 and partial.result == "incorrect"
    assert partial.errors == {"k4": ErrorType.KNOWLEDGE}
    assert partial.correct_answer == EXPLAIN.model_answer

    empty = open_question.grade(activity, {"text": "  "})
    assert empty.score == 0 and empty.errors == {"k4": ErrorType.FORGOTTEN}


def test_open_question_graded_by_the_evaluator(math: ReferenceLesson, registry: ActivityRegistry) -> None:
    unit = with_material(math.unit("k4"), open_questions=[EXPLAIN])
    activity = registry.get(ActivityCode.OPEN_QUESTION).build([unit], 2, random.Random(1))
    open_question = registry.get(ActivityCode.OPEN_QUESTION)
    assert isinstance(open_question, OpenQuestionActivity)
    evaluation = OpenEvaluation(
        score=0.67,
        key_points_found=["même dénominateur", "5 est plus grand que 3", "un point inventé"],
        error_type=ErrorType.IMPRECISION,
        feedback="Presque ! Tu as vu que les dénominateurs sont égaux.",
        confidence=0.9,
    )
    grade = open_question.grade_with(activity, {"text": "Même dénominateur et 5 > 3"}, evaluation)
    assert grade.score == 0.67 and grade.result == "partial"
    assert grade.explanation == evaluation.feedback
    assert [d["found"] for d in grade.details] == [True, False, True]  # le point inventé est ignoré
    assert grade.errors == {"k4": ErrorType.IMPRECISION}


@pytest.mark.parametrize(
    ("answer", "point", "found"),
    [
        ("On compare les numérateurs", "on compare les numérateurs", True),
        ("on regarde les numerateurs pour comparer", "on compare les numérateurs", True),
        ("Les dénominateurs", "on compare les numérateurs", False),
        ("", "même dénominateur", False),
    ],
)
def test_key_point_detection(answer: str, point: str, found: bool) -> None:
    assert point_found(answer, point) is found


def test_composer_deepens_a_mastered_notion_with_an_open_question(
    math: ReferenceLesson, registry: ActivityRegistry
) -> None:
    unit = with_material(math.unit("k4"), open_questions=[EXPLAIN])
    mastered = Mastery(85, 3, NOW - timedelta(hours=1), NOW - timedelta(days=4), levels=frozenset({1, 2, 3}))
    plan = SessionComposer(registry).compose([unit], {"k4": mastered}, NOW, seed=3)
    first = plan.items[0].activity
    assert (first.type, cognitive_level(first.type, first.difficulty)) == (ActivityCode.OPEN_QUESTION, 4)
    # Jamais en première séance ni dans la reprise des erreurs.
    first_session = SessionComposer(registry).compose([unit], {}, NOW, seed=3)
    assert ActivityCode.OPEN_QUESTION not in {i.activity.type for i in first_session.items}


# --------------------------------------------------------------------------- #
# Types d'erreurs
# --------------------------------------------------------------------------- #


def test_the_chosen_distractor_tells_the_error(math: ReferenceLesson, registry: ActivityRegistry) -> None:
    unit = math.unit("k4")
    question = unit.material.questions_of(1)[0]
    tagged = question.model_copy(update={"misconceptions": ["confusion", None, "calculation"]})
    unit = with_material(unit, questions=[tagged])
    mcq = registry.get(ActivityCode.MCQ)
    activity = mcq.build([unit], 1, random.Random(4))
    choice_of = {c["text"]: c["id"] for c in activity.payload["choices"]}
    errors = [mcq.grade(activity, {"choice_id": choice_of[d]}).errors["k4"] for d in tagged.distractors]
    assert errors == [ErrorType.CONFUSION, ErrorType.KNOWLEDGE, ErrorType.CALCULATION]
    assert mcq.grade(activity, {"choice_id": activity.solution["choice_id"]}).errors == {}


@pytest.mark.parametrize(
    ("given", "error"),
    [
        ("", ErrorType.FORGOTTEN),
        ("Je ne sais pas", ErrorType.FORGOTTEN),
        ("1788", ErrorType.IMPRECISION),
        ("numerotateur", ErrorType.IMPRECISION),
        ("Napoléon", ErrorType.KNOWLEDGE),
    ],
)
def test_written_answer_errors(given: str, error: ErrorType) -> None:
    assert written_answer_error(given, ["1789", "numérateur"]) is error


def test_other_activities_errors(history: ReferenceLesson, registry: ActivityRegistry) -> None:
    unit = history.unit("k1")
    card = registry.get(ActivityCode.FLASHCARD).build([unit], 2, random.Random(1))
    grade = registry.for_activity(card).grade(card, {"self_assessment": "didnt_know"})
    assert grade.errors == {"k1": ErrorType.FORGOTTEN}
    units = [history.unit(k) for k in ("k1", "k3", "k4")]
    match = registry.get(ActivityCode.MATCH).build(units, 2, random.Random(1))
    grade = registry.for_activity(match).grade(match, {"pairs": []})
    assert grade.errors == dict.fromkeys(("k1", "k3", "k4"), ErrorType.CONFUSION)


def test_fast_wrong_answers_are_random() -> None:
    assert with_speed(ErrorType.KNOWLEDGE, 900) is ErrorType.RANDOM
    assert with_speed(ErrorType.CONFUSION, 4000) is ErrorType.CONFUSION
    assert with_speed(ErrorType.CONFUSION, None) is ErrorType.CONFUSION


def test_recurring_errors() -> None:
    def seen(knowledge: str, error: ErrorType, session: str, days_ago: int) -> ErrorOccurrence:
        return ErrorOccurrence(knowledge, error, session, NOW - timedelta(days=days_ago))

    occurrences = [
        *(seen("k2", ErrorType.CONFUSION, s, d) for s, d in (("s1", 9), ("s2", 5), ("s3", 1))),
        seen("k2", ErrorType.CONFUSION, "s3", 1),  # même séance : ne compte qu'une fois
        *(seen("k4", ErrorType.FORGOTTEN, s, d) for s, d in (("s1", 9), ("s2", 5))),  # 2 séances
        *(seen("k5", ErrorType.RANDOM, s, d) for s, d in (("s1", 9), ("s2", 5), ("s3", 1))),
        *(
            seen("k1", ErrorType.IMPRECISION, s, d)
            for s, d in (("s4", 20), ("s5", 19), ("s6", 18), ("s7", 17))
        ),
    ]
    found = recurring_errors(occurrences)
    assert [(r.knowledge_id, r.error_type, r.sessions) for r in found] == [
        ("k1", ErrorType.IMPRECISION, 4),
        ("k2", ErrorType.CONFUSION, 3),
    ]
    assert found[1].last_at == NOW - timedelta(days=1)


@pytest.mark.parametrize(
    ("shown", "answer", "revealed"),
    [
        ("On compare leurs numérateurs.", "numérateur", True),  # pluriel
        ("Regarde le numérateur.", "numérateur", True),
        ("Regarde le nombre du haut.", "numérateur", False),
        ("Quelle fraction : 2/7 ou 6/7 ?", "5/8", False),
        ("5/8 est plus grand que 3/8.", "5/8", True),
        ("Celle qui a le plus grand numérateur", "Celle qui a le plus grand numérateur", True),
        ("On regarde le numérateur le plus grand.", "Celle qui a le plus grand numérateur", False),
        ("", "1789", False),
    ],
)
def test_reveals(shown: str, answer: str, revealed: bool) -> None:
    assert reveals(shown, answer) is revealed
