"""Règles d’écriture adaptées séparément aux neuf classes."""

from app.domain.instructions import writing_rules
from app.domain.knowledge import Grade


def test_each_grade_has_its_own_writing_rules() -> None:
    rules = {grade: writing_rules(grade.value) for grade in Grade}
    assert len(set(rules.values())) == 9
    assert all(rules.values())


def test_unknown_grade_uses_a_safe_middle_school_default() -> None:
    assert writing_rules("niveau-inconnu") == writing_rules("6e")
