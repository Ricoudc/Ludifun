"""Étape 13 : niveaux de compréhension, niveau de maîtrise affiché et compétences.

Critère de fin : réussir des QCM, même cinq séances de suite, ne suffit plus pour
« maîtrisée » ; il faut aussi retrouver la réponse seul (et appliquer une règle).
"""

import random
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.activities.base import ActivityCode, BuiltActivity
from app.domain.activities.registry import ActivityRegistry
from app.domain.composer import Block, SessionComposer
from app.domain.mastery import Mastery
from app.domain.scoring import Evidence, evidences_from, summarize_session, validated_levels
from app.domain.simulated_pupil import respond
from app.domain.understanding import (
    MasteryLevel,
    cognitive_level,
    level_color,
    notion_level,
    required_levels,
    skill_level,
)
from tests.domain.conftest import ReferenceLesson

NOW = datetime(2026, 9, 24, 17, 0, tzinfo=UTC)


def mastery(score: int, box: int = 3, levels: frozenset[int] = frozenset()) -> Mastery:
    return Mastery(score, box, NOW + timedelta(days=3), NOW - timedelta(days=1), levels=levels)


# --------------------------------------------------------------------------- #
# Niveau sollicité par une activité et niveaux exigés par notion
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("code", "difficulty", "level"),
    [
        (ActivityCode.MCQ, 1, 1),
        (ActivityCode.MCQ, 2, 1),  # QCM inversé : on reconnaît encore la bonne réponse
        (ActivityCode.MCQ, 3, 3),  # relier, appliquer
        (ActivityCode.TRUE_FALSE, 1, 1),
        (ActivityCode.MATCH, 2, 1),
        (ActivityCode.SPEED_CHALLENGE, 1, 1),
        (ActivityCode.FILL_BLANK, 2, 2),
        (ActivityCode.FLASHCARD, 2, 2),
    ],
)
def test_cognitive_level_of_activities(code: ActivityCode, difficulty: int, level: int) -> None:
    assert cognitive_level(code, difficulty) == level


def test_required_levels_follow_the_material_and_the_type(
    history: ReferenceLesson, math: ReferenceLesson, science: ReferenceLesson, registry: ActivityRegistry
) -> None:
    # Une date se reconnaît et se rappelle ; une règle s'applique, si la leçon le permet.
    assert required_levels(history.unit("k1"), registry) == {1, 2}
    assert required_levels(math.unit("k4"), registry) == {1, 2, 3}
    # Terme : jamais « appliquer », même si une question difficile existait.
    assert required_levels(math.unit("k2"), registry) == {1, 2}
    # Classification sans texte à trous ni carte : on n'exige pas un niveau impossible à prouver.
    assert required_levels(science.unit("k1"), registry) == {1}


def test_every_reference_notion_can_reach_its_required_levels(
    lesson: ReferenceLesson, registry: ActivityRegistry
) -> None:
    for unit in lesson.units.values():
        reachable = {cognitive_level(code, d) for code, d in registry.single_options(unit)} | {1}
        assert required_levels(unit, registry) <= reachable


# --------------------------------------------------------------------------- #
# Niveaux validés pendant une séance
# --------------------------------------------------------------------------- #


def evidence(knowledge_id: str, result: float, level: int, weight: float = 1.0) -> Evidence:
    return Evidence(knowledge_id, result, weight, ActivityCode.MCQ, cognitive_level=level)


def test_a_level_is_validated_at_80_percent_of_its_answers() -> None:
    validated = validated_levels(
        [
            evidence("k1", 1.0, 1),
            evidence("k1", 1.0, 2),
            evidence("k1", 0.0, 2, weight=0.5),  # 2 réponses de niveau 2 : 1/1,5 = 67 %
            evidence("k2", 1.0, 1),
            evidence("k2", 1.0, 2),
        ]
    )
    assert validated == {"k1": {1}, "k2": {1, 2}}


def test_validated_levels_are_kept_from_one_session_to_the_next() -> None:
    before = {"k1": mastery(70, levels=frozenset({2}))}
    outcome = summarize_session(
        [1.0], [evidence("k1", 1.0, 1)], before, {"k1": 5}, NOW, {"k1": frozenset({1, 2})}
    )
    assert outcome.results[0].mastery.levels == {1, 2}


# --------------------------------------------------------------------------- #
# Niveau affiché 0 à 5
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("state", "level"),
    [
        (None, MasteryLevel.NEVER),
        (mastery(20, levels=frozenset({1, 2})), MasteryLevel.DISCOVERED),
        (mastery(45, levels=frozenset({1, 2})), MasteryLevel.FRAGILE),
        (mastery(70, levels=frozenset({1, 2})), MasteryLevel.LEARNING),
        (mastery(100, box=5, levels=frozenset({1})), MasteryLevel.LEARNING),  # jamais retrouvée seul
        (mastery(85, box=3, levels=frozenset({1, 2})), MasteryLevel.MASTERED),
        (mastery(95, box=4, levels=frozenset({1, 2})), MasteryLevel.MASTERED),  # pas encore à J+14
        (mastery(95, box=5, levels=frozenset({1, 2})), MasteryLevel.SOLID),
    ],
)
def test_displayed_level(state: Mastery | None, level: MasteryLevel) -> None:
    assert notion_level(state, {1, 2}).level is level


def test_explanations_name_what_is_missing() -> None:
    assert "retrouver seul" in notion_level(mastery(90, levels=frozenset({1})), {1, 2}).explanation
    assert "appliquer" in notion_level(mastery(90, levels=frozenset({1, 2})), {1, 2, 3}).explanation
    assert notion_level(mastery(90, levels=frozenset({1})), {1, 2}).missing == {2}
    assert notion_level(None, {1}).explanation == "Pas encore travaillée."


def test_colors_and_skill_levels() -> None:
    assert [level_color(level) for level in range(6)] == ["grey", "red", "red", "orange", "green", "green"]
    assert skill_level([]) is MasteryLevel.NEVER
    assert skill_level([4, 4, 5]) is MasteryLevel.MASTERED
    assert skill_level([5, 5, 2]) is MasteryLevel.LEARNING  # moyenne 4, mais une notion fragile
    assert skill_level([5, 4, 2]) is MasteryLevel.LEARNING  # moyenne 3,67
    assert skill_level([5, 5, 3]) is MasteryLevel.MASTERED


# --------------------------------------------------------------------------- #
# Critère de fin de l'étape 13
# --------------------------------------------------------------------------- #


def everything(_: str) -> bool:
    return True


def nothing(_: str) -> bool:
    return False


def play(
    registry: ActivityRegistry, activities: list[BuiltActivity], recalls: bool
) -> tuple[list[float], list[Evidence]]:
    """Un élève qui reconnaît toujours la bonne réponse, et ne la retrouve seul que si `recalls`."""
    scores, evidences = [], []
    for activity in activities:
        knows = everything if recalls or cognitive_level(activity.type, activity.difficulty) == 1 else nothing
        grade = registry.for_activity(activity).grade(activity, respond(activity, knows))
        scores.append(grade.score)
        evidences += evidences_from(activity, grade, registry)
    return scores, evidences


def test_five_successful_mcq_sessions_are_not_mastery(
    math: ReferenceLesson, registry: ActivityRegistry
) -> None:
    unit = math.unit("k2")  # Numérateur : QCM, texte à trous et carte mémoire possibles
    mcq = registry.get(ActivityCode.MCQ)
    required = {"k2": required_levels(unit, registry)}
    masteries: dict[str, Mastery] = {}
    for day in range(5):
        activity = mcq.build([unit], 1, random.Random(day))
        scores, evidences = play(registry, [activity], recalls=False)
        now = NOW + timedelta(days=day * 3)
        outcome = summarize_session(scores, evidences, masteries, {"k2": 5}, now, required)
        masteries = {"k2": outcome.results[0].mastery}

    level = outcome.results[0].level
    assert masteries["k2"].score == 100 and masteries["k2"].box == 5
    assert level.level is MasteryLevel.LEARNING  # et non « maîtrisée »
    assert level.missing == {2}
    assert "retrouver seul" in level.explanation
    assert not outcome.lesson_mastered

    # La révision suivante le fait travailler au niveau manquant…
    later = NOW + timedelta(days=30)
    plan = SessionComposer(registry).compose([unit], masteries, later, seed=1)
    first = plan.items[0].activity
    assert plan.items[0].block is Block.WARMUP
    assert cognitive_level(first.type, first.difficulty) == 2

    # …et une réussite sans aide suffit alors pour « très bien maîtrisée ».
    scores, evidences = play(registry, [first], recalls=True)
    outcome = summarize_session(scores, evidences, masteries, {"k2": 5}, later, required)
    assert outcome.results[0].previous_level.level is MasteryLevel.LEARNING
    assert outcome.results[0].level.level is MasteryLevel.SOLID
    assert outcome.lesson_mastered


def test_a_rule_must_be_applied(math: ReferenceLesson, registry: ActivityRegistry) -> None:
    unit = math.unit("k4")  # Comparer des fractions de même dénominateur
    known = mastery(95, box=5, levels=frozenset({1, 2}))
    assert notion_level(known, required_levels(unit, registry)).level is MasteryLevel.LEARNING
    plan = SessionComposer(registry).compose([unit], {"k4": known}, NOW, seed=4)
    first = plan.items[0].activity
    assert (first.type, first.difficulty) == (ActivityCode.MCQ, 3)


def test_a_notion_known_at_every_level_is_left_alone(
    history: ReferenceLesson, registry: ActivityRegistry
) -> None:
    units = list(history.units.values())
    solid = {u.id: mastery(95, box=5, levels=frozenset({1, 2, 3})) for u in units}
    only_mcq = {**solid, "k1": mastery(95, box=5, levels=frozenset({1}))}
    plan = SessionComposer(registry).compose(units, only_mcq, NOW, seed=2)
    assert plan.items[0].activity.knowledge_ids == ["k1"]
    worked = {
        k for i in plan.items if i.block in (Block.WARMUP, Block.CORE) for k in i.activity.knowledge_ids
    }
    assert worked == {"k1"}
