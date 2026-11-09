"""§5.72 : après deux échecs, revenir d'abord sur une notion préalable pas encore maîtrisée."""

import random
from datetime import UTC, datetime

from app.domain.activities.base import ActivityCode
from app.domain.activities.registry import ActivityRegistry
from app.domain.composer import EASY, Block, SessionComposer
from app.domain.decisions import Rule, describe
from app.domain.knowledge import (
    KnowledgeItem,
    KnowledgeMaterial,
    KnowledgeType,
    KnowledgeUnit,
    Relation,
    RelationType,
    Theme,
)
from app.domain.mastery import Mastery
from app.domain.prerequisites import THEME_PREREQUISITES, prerequisite_of
from app.domain.rules import RULES
from tests.domain.conftest import ReferenceLesson

NOW = datetime(2026, 11, 9, tzinfo=UTC)
BELOW = RULES.adaptation.prerequisite_below


def unit(
    kid: str, theme: Theme | None, importance: int = 3, relations: list[Relation] | None = None
) -> KnowledgeUnit:
    item = KnowledgeItem(
        id=kid,
        type=KnowledgeType.FACT,
        label=f"Notion {kid}",
        statement=f"Phrase {kid}.",
        importance=importance,
        source_excerpt=kid,
        theme=theme,
        relations=relations or [],
    )
    return KnowledgeUnit(item=item, material=KnowledgeMaterial(knowledge_id=kid, explanation="Relis."))


def mastered(score: int) -> Mastery:
    return Mastery(score=score, box=3, next_review_at=NOW, last_practiced_at=NOW)


def test_division_goes_back_to_multiplication_not_yet_mastered() -> None:
    division, tables, other = (
        unit("k1", Theme.DIVISION),
        unit("k2", Theme.MULTIPLICATION),
        unit("k3", Theme.AREA),
    )
    units = [division, tables, other]
    assert prerequisite_of(division, units, {}, BELOW) == tables  # jamais travaillée : 0
    assert prerequisite_of(division, units, {"k2": mastered(BELOW - 1)}, BELOW) == tables
    assert prerequisite_of(division, units, {"k2": mastered(BELOW)}, BELOW) is None  # déjà sue


def test_no_prerequisite_without_link() -> None:
    lone = unit("k1", Theme.ADDITION)
    assert prerequisite_of(lone, [lone, unit("k2", Theme.DIVISION)], {}, BELOW) is None
    untagged = unit("k1", None)
    assert prerequisite_of(untagged, [untagged, unit("k2", Theme.ADDITION)], {}, BELOW) is None


def test_example_of_points_to_the_general_rule_first() -> None:
    example = unit("k1", Theme.CONJUGATION, relations=[Relation(type=RelationType.EXAMPLE_OF, target="k3")])
    units = [example, unit("k2", Theme.WORD_NATURE), unit("k3", Theme.CONJUGATION)]
    assert prerequisite_of(example, units, {}, BELOW) == units[2]


def test_the_weakest_then_the_most_important() -> None:
    fractions = unit("k1", Theme.FRACTIONS, relations=[])
    percent = unit("k0", Theme.PERCENT)
    proportion = unit("k2", Theme.PROPORTION, importance=5)
    units = [percent, fractions, proportion]
    assert prerequisite_of(percent, units, {}, BELOW) == proportion  # à égalité : la plus importante
    assert prerequisite_of(percent, units, {"k2": mastered(50), "k1": mastered(20)}, BELOW) == fractions


def test_the_map_has_no_cycle() -> None:
    def reaches(start: Theme, goal: Theme, seen: frozenset[Theme] = frozenset()) -> bool:
        return any(
            t == goal or (t not in seen and reaches(t, goal, seen | {t}))
            for t in THEME_PREREQUISITES.get(start, ())
        )

    assert not any(reaches(theme, theme) for theme in THEME_PREREQUISITES)


def test_remediation_starts_with_the_prerequisite(
    history: ReferenceLesson, registry: ActivityRegistry
) -> None:
    composer = SessionComposer(registry)
    failed_unit, before = history.unit("k3"), history.unit("k1")
    failed = [registry.get(ActivityCode.MCQ).build([failed_unit], 1, random.Random(1))]
    planned = composer.remediation(failed_unit, failed, start_position=4, seed=7, prerequisite=before)
    assert [p.position for p in planned] == [4, 5, 6]
    assert {p.block for p in planned} == {Block.REMEDIATION}
    first, *rest = planned
    assert first.activity.knowledge_ids == ["k1"] and first.activity.type in EASY
    assert first.reason["rule"] == Rule.PREREQUISITE
    text = describe(first.reason)
    assert text is not None and "on revient d'abord sur" in text and before.item.label in text
    assert all(p.activity.knowledge_ids == ["k3"] and p.reason["rule"] == Rule.REMEDIATION for p in rest)
    # Sans notion préalable : la remédiation d'avant, inchangée.
    assert len(composer.remediation(failed_unit, failed, start_position=4, seed=7)) == 2
