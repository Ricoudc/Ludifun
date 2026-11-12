"""Leçons de référence (cahier des charges §139) : pour chaque niveau et matière, l'entrée, les
notions et compétences attendues, les activités possibles et le comportement attendu du moteur.

Les leçons (`reference_lessons/*.json`) sont aussi jouées par tous les tests paramétrés
(validation, activités, composeur) : ce fichier fixe ce que chacune doit en plus démontrer.
"""

import itertools
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.activities.base import ActivityCode
from app.domain.activities.registry import ActivityRegistry
from app.domain.composer import Block, NothingToReview, SessionComposer
from app.domain.knowledge import Grade, KnowledgeType, KnowledgeUnit, Subject
from app.domain.mastery import Mastery
from app.domain.understanding import CognitiveLevel, required_levels
from tests.domain.conftest import load_lesson
from tests.domain.test_session_simulation import run_session

NOW = datetime(2026, 9, 25, 17, 0, tzinfo=UTC)
A = ActivityCode


@dataclass(frozen=True)
class Expected:
    subject: Subject
    grade: Grade
    types: dict[str, KnowledgeType]  # notions attendues et leur type
    skills: int
    activities: frozenset[ActivityCode]  # activités qui doivent pouvoir être construites
    first_puzzle: ActivityCode  # jeu à plusieurs notions de la première séance


EXPECTED = {
    "french_cp_vowels.json": Expected(
        Subject.FRENCH,
        Grade.CP,
        {"k1": KnowledgeType.FACT, "k2": KnowledgeType.CLASSIFICATION, "k3": KnowledgeType.TERM,
         "k4": KnowledgeType.TERM, "k5": KnowledgeType.FACT},
        skills=2,
        activities=frozenset({A.MCQ, A.TRUE_FALSE, A.CLASSIFY, A.MATCH}),
        first_puzzle=ActivityCode.MATCH,
    ),
    "geography_6e_continents.json": Expected(
        Subject.GEOGRAPHY,
        Grade.SIXIEME,
        {"k1": KnowledgeType.CLASSIFICATION, "k2": KnowledgeType.PLACE, "k3": KnowledgeType.PLACE,
         "k4": KnowledgeType.PLACE, "k5": KnowledgeType.PLACE, "k6": KnowledgeType.FACT},
        skills=2,
        activities=frozenset({A.MAP, A.COLORING, A.CLASSIFY, A.MEMORY}),
        first_puzzle=ActivityCode.MAP,
    ),
    "math_3e_pythagoras.json": Expected(
        Subject.MATH,
        Grade.TROISIEME,
        {"k1": KnowledgeType.FORMULA, "k2": KnowledgeType.TERM, "k3": KnowledgeType.RULE,
         "k4": KnowledgeType.PROCESS, "k5": KnowledgeType.FACT, "k6": KnowledgeType.TERM},
        skills=2,
        activities=frozenset({A.MCQ, A.ORDER, A.FILL_BLANK, A.MATCH}),
        first_puzzle=ActivityCode.MATCH,
    ),
}  # fmt: skip


def buildable(units: list[KnowledgeUnit], registry: ActivityRegistry) -> set[ActivityCode]:
    single = {code for unit in units for code, _ in registry.single_options(unit)}
    multi = {
        t.code
        for t in registry.all()
        if t.multi_knowledge
        and any(
            t.can_build(list(group), d)
            for d in t.difficulties
            for n in range(t.min_units, t.max_units + 1)
            for group in itertools.combinations(units, n)
        )
    }
    return single | multi


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_reference_lesson_is_understood_and_playable(name: str, registry: ActivityRegistry) -> None:
    lesson, expected = load_lesson(name), EXPECTED[name]
    assert lesson.analysis.lesson is not None
    assert (lesson.analysis.lesson.subject, lesson.analysis.lesson.grade) == (
        expected.subject,
        expected.grade,
    )
    assert {k.id: k.type for k in lesson.analysis.knowledge} == expected.types
    assert len(lesson.analysis.skills) == expected.skills
    units = list(lesson.units.values())
    assert expected.activities <= buildable(units, registry)

    plan = SessionComposer(registry).compose(units, {}, NOW, seed=1)
    assert [i.activity.type for i in plan.items if i.block is Block.MATCH] == [expected.first_puzzle]
    assert all(i.reason for i in plan.items)  # chaque choix a sa raison (§126)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_a_pupil_who_learns_masters_the_lesson(name: str, registry: ActivityRegistry) -> None:
    """Comportement attendu : un élève qui se trompe sur une notion puis l'apprend finit par tout
    maîtriser, et la notion ratée revient plus tôt que les autres."""
    lesson = load_lesson(name)
    units = list(lesson.units.values())
    composer = SessionComposer(registry)
    weak = max(units, key=lambda u: u.item.importance).id
    outcome, _ = run_session(composer, units, {}, NOW, lambda k: k != weak, seed=2)
    masteries: dict[str, Mastery] = {r.knowledge_id: r.mastery for r in outcome.results}
    assert masteries[weak].score < min(m.score for k, m in masteries.items() if k != weak)
    assert masteries[weak].next_review_at <= min(m.next_review_at for m in masteries.values())

    now = NOW
    for day in range(1, 30):
        now = NOW + timedelta(days=day)
        try:
            outcome, _ = run_session(composer, units, masteries, now, lambda _: True, seed=day)
        except NothingToReview:  # tout est su, rien n'est dû ce jour-là
            continue
        masteries = {**masteries, **{r.knowledge_id: r.mastery for r in outcome.results}}
    for unit in units:
        mastery = masteries[unit.id]
        assert mastery.score >= 80, (name, unit.id, mastery.score)
        assert required_levels(unit, registry) <= mastery.levels, (name, unit.id)


def test_the_maths_lesson_asks_to_apply() -> None:
    """3e maths : le théorème et la méthode doivent être appliqués, pas seulement récités."""
    lesson = load_lesson("math_3e_pythagoras.json")
    registry = ActivityRegistry(
        list(__import__("app.domain.activities.registry").domain.activities.registry.default_registry().all())
    )
    assert CognitiveLevel.APPLY in required_levels(lesson.unit("k1"), registry)
