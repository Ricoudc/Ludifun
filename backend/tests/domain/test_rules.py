"""Règles du moteur dans engine_rules.toml (CDC §125, §138) et raisons des choix (§126)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain import composer, engagement, help, mastery
from app.domain.activities.registry import ActivityRegistry
from app.domain.composer import SessionComposer
from app.domain.decisions import Rule, describe, reason
from app.domain.mastery import Mastery
from app.domain.rules import DEFAULT_FILE, ENGINE_VERSION, load_rules
from tests.domain.conftest import ReferenceLesson

NOW = datetime(2026, 9, 25, 17, 0, tzinfo=UTC)


def test_the_engine_reads_its_rules_from_the_file() -> None:
    rules = load_rules()
    assert rules.version == ENGINE_VERSION
    assert rules.session.level_up_score == composer.LEVEL_UP_SCORE
    assert rules.adaptation.remediation_after_failures == engagement.REMEDIATION_AFTER_FAILURES
    assert (
        mastery.REVIEW_INTERVAL_DAYS == rules.mastery.review_interval_days == {1: 1, 2: 2, 3: 4, 4: 7, 5: 14}
    )
    assert help.HELP_RESULT_FACTOR[3] == 0.75


def test_a_wrong_rules_file_is_refused(tmp_path: Path) -> None:
    text = DEFAULT_FILE.read_text(encoding="utf-8")
    bad = tmp_path / "rules.toml"
    bad.write_text(text.replace("failure_below = 0.5", "failure_below = 5"), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_rules(bad)
    missing = tmp_path / "missing.toml"
    missing.write_text(text.replace(', "5" = 14', ""), encoding="utf-8")
    with pytest.raises(ValueError, match="review_interval_days"):
        load_rules(missing)
    unknown = tmp_path / "unknown.toml"
    unknown.write_text(text + "\n[nouveau]\nseuil = 1\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_rules(unknown)


def test_review_activities_say_why(history: ReferenceLesson, registry: ActivityRegistry) -> None:
    units = list(history.units.values())
    due = NOW - timedelta(days=1)
    masteries = {u.id: Mastery(60, 2, due, due - timedelta(days=2), levels=frozenset({1})) for u in units}
    plan = SessionComposer(registry).compose(units, masteries, NOW, seed=3)
    rules = {item.reason["rule"] for item in plan.items}
    assert Rule.LEVEL_UP in rules  # score 60 ≥ 50 et « se rappeler » pas encore validé
    level_up = next(i for i in plan.items if i.reason["rule"] == Rule.LEVEL_UP)
    assert level_up.reason["facts"] == {"score": 60, "threshold": 50, "level": 2}
    assert describe(level_up.reason) == "Score 60 ≥ 50 : il reste à valider le niveau « se rappeler »."
    assert all(describe(i.reason) for i in plan.items)


def test_descriptions() -> None:
    assert describe(None) is None
    assert describe(reason(Rule.BY_SCORE, score=30, due=True, difficulty=1)) == (
        "Révision prévue aujourd'hui (score 30) : difficulté 1."
    )
    assert describe(reason(Rule.PAUSE_STRUGGLING, failures=4)) == "4 échecs d'affilée : pause proposée."
