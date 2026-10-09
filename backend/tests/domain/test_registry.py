import pytest

from app.domain.activities.base import ActivityCode
from app.domain.activities.mcq import Mcq
from app.domain.activities.registry import ActivityRegistry, UnknownActivity
from app.domain.knowledge import KnowledgeType
from tests.domain.conftest import ReferenceLesson

V1_CODES = {
    ActivityCode.MCQ,
    ActivityCode.TRUE_FALSE,
    ActivityCode.FILL_BLANK,
    ActivityCode.MATCH,
    ActivityCode.SPEED_CHALLENGE,
    ActivityCode.FLASHCARD,
    ActivityCode.OPEN_QUESTION,  # étape 14
}
GRAPHIC_CODES = {
    ActivityCode.ORDER,
    ActivityCode.TIMELINE,
    ActivityCode.CLASSIFY,
    ActivityCode.MEMORY,
}  # étape 21
FIGURE_CODES = {ActivityCode.MAP, ActivityCode.COLORING}  # étape 22
SPELLING_CODES = {
    ActivityCode.WORD_FLASH,
    ActivityCode.SCRAMBLE,
    ActivityCode.DICTATION,
}  # listes de mots à écrire
EXTRA_CODES = {
    ActivityCode.UNJUMBLE,
    ActivityCode.FIND_MATCH,
    ActivityCode.WHEEL,
    ActivityCode.BOX,
    ActivityCode.RANDOM_CARDS,
}  # étape 26
PICTURE_CODES = {ActivityCode.PICTURE_MATCH, ActivityCode.PICTURE_FIND}  # étape 28
GEOMETRY_CODES = {ActivityCode.ALIGN}  # figure dessinée par le code
MATH_CODES = {ActivityCode.NUMBER_LINE, ActivityCode.FRACTION_BAR, ActivityCode.COLUMN_OP}  # calculés


def test_registry_holds_every_activity(registry: ActivityRegistry) -> None:
    assert (
        set(registry.codes)
        == V1_CODES
        | GRAPHIC_CODES
        | FIGURE_CODES
        | SPELLING_CODES
        | EXTRA_CODES
        | PICTURE_CODES
        | GEOMETRY_CODES
        | MATH_CODES
        == set(ActivityCode)
    )
    assert all(registry.get(code).code == code for code in registry.codes)


@pytest.mark.parametrize("code", ["PUZZLE", "DRAWING", ""])
def test_unimplemented_or_unknown_activity(registry: ActivityRegistry, code: str) -> None:
    with pytest.raises(UnknownActivity):
        registry.get(code)


def test_an_activity_cannot_be_registered_twice() -> None:
    with pytest.raises(ValueError, match="deux fois"):
        ActivityRegistry([Mcq(), Mcq()])


def test_evidence_factors(registry: ActivityRegistry) -> None:
    """§9.3 : vrai/faux, défi rapide, cartes mémoire (seules ou tirées au hasard) et memory
    (chance, place des cartes) comptent pour moitié."""
    halved = {t.code for t in registry.all() if t.evidence_factor == 0.5}
    assert halved == {
        ActivityCode.TRUE_FALSE,
        ActivityCode.SPEED_CHALLENGE,
        ActivityCode.FLASHCARD,
        ActivityCode.MEMORY,
        ActivityCode.RANDOM_CARDS,
    }


def test_compatibility_matrix(registry: ActivityRegistry) -> None:
    """Quelques cases de la matrice §7.2."""
    get = registry.get
    assert KnowledgeType.PERSON not in get("FILL_BLANK").knowledge_types
    assert KnowledgeType.PROCESS not in get("MATCH").knowledge_types
    assert KnowledgeType.FORMULA not in get("SPEED_CHALLENGE").knowledge_types
    assert KnowledgeType.EVENT not in get("FLASHCARD").knowledge_types
    assert get("MCQ").knowledge_types == frozenset(KnowledgeType)


def test_important_notions_have_at_least_two_activities(
    lesson: ReferenceLesson, registry: ActivityRegistry
) -> None:
    """Règle §5.3 : une notion d'importance ≥ 4 doit permettre au moins 2 activités."""
    for unit in lesson.units.values():
        if unit.item.importance >= 4:
            assert len(registry.single_options(unit)) >= 2, unit.id


def test_every_notion_can_be_practised(lesson: ReferenceLesson, registry: ActivityRegistry) -> None:
    for unit in lesson.units.values():
        assert registry.single_options(unit), unit.id
