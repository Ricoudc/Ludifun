"""§5.74 : exercice neuf sur une erreur qui revient. L'IA propose, le code garde ce qui est prouvé."""

import random
from datetime import UTC, datetime

from app.domain.activities.base import ActivityCode
from app.domain.activities.registry import ActivityRegistry
from app.domain.errors import ErrorType, RecurringError
from app.domain.knowledge import MaterialQuestion
from app.domain.targeted_practice import ProposedTarget, Target, check_targets, targets
from tests.domain.conftest import ReferenceLesson

NOW = datetime(2026, 11, 9, tzinfo=UTC)


def recurring(key: str, error: ErrorType, sessions: int = 3) -> RecurringError:
    return RecurringError(key, error, sessions, NOW)


def test_one_target_per_notion_and_not_twice(history: ReferenceLesson) -> None:
    units = list(history.units.values())
    found = targets(
        [
            recurring("k3", ErrorType.CONFUSION, 4),
            recurring("k3", ErrorType.KNOWLEDGE),
            recurring("k9", ErrorType.CONFUSION),  # notion d'une autre leçon
            recurring("k1", ErrorType.RANDOM),  # le hasard n'est pas une erreur sur la notion
            recurring("k2", ErrorType.FORGOTTEN),
        ],
        units,
        limit=5,
    )
    assert [(t.unit.id, t.error) for t in found] == [("k3", ErrorType.CONFUSION), ("k2", ErrorType.FORGOTTEN)]
    assert targets([recurring("k3", ErrorType.CONFUSION)], units, limit=1)[0].label.startswith("Confond")

    done = history.unit("k3")
    question = MaterialQuestion(
        difficulty=1,
        stem="Q ?",
        answer="1789",
        distractors=["1788", "1790", "1791"],
        target_error="confusion",
    )
    marked = done.model_copy(
        update={
            "material": done.material.model_copy(update={"questions": [*done.material.questions, question]})
        }
    )
    assert targets([recurring("k3", ErrorType.CONFUSION)], [marked]) == []


def test_only_proved_answers_are_kept(history: ReferenceLesson) -> None:
    target = Target(history.unit("k3"), ErrorType.CONFUSION)
    checked = check_targets(
        target,
        [
            ProposedTarget(
                "En quelle année les États généraux sont-ils réunis ?",
                "1789",
                ["1792", "1799", "1815"],
                1,
                trap="1792",
                why="1792, c'est la proclamation de la République.",
            ),
            ProposedTarget(
                "Qui présidait les États généraux ?", "Necker", ["Robespierre", "Danton", "Marat"], 1
            ),
            ProposedTarget("Combien de jours dura la réunion ?", "1789", ["1789", "1790", "1791"], 1),
        ],
        limit=2,
    )
    assert len(checked.questions) == 1
    kept = checked.questions[0]
    assert kept.target_error == "confusion" and kept.target_why is not None
    assert kept.misconception_of("1792") == "confusion" and kept.misconception_of("1815") is None
    reasons = [r.reason for r in checked.rejected]
    assert "bonne réponse ni dans la leçon ni dans un calcul vérifié" in reasons  # Necker : mémoire de l'IA
    assert len(reasons) == 2


def test_a_calculation_is_redone_by_the_code(history: ReferenceLesson) -> None:
    target = Target(history.unit("k1"), ErrorType.CALCULATION)
    right = ProposedTarget("Combien font 47 + 38 ?", "85", ["75", "815", "84"], 1, trap="75")
    wrong = ProposedTarget("Combien font 47 + 38 ?", "86", ["75", "815", "84"], 1)
    two = ProposedTarget("Combien font 3 + 4 puis 5 + 6 ?", "11", ["7", "12", "10"], 1)
    checked = check_targets(target, [right, wrong, two], limit=5)
    assert [q.answer for q in checked.questions] == ["85"]
    assert len(checked.rejected) == 2


def test_the_mcq_prefers_the_targeted_question(history: ReferenceLesson, registry: ActivityRegistry) -> None:
    unit = history.unit("k3")
    question = MaterialQuestion(
        difficulty=1,
        stem="En quelle année les États généraux sont-ils réunis ?",
        answer="1789",
        distractors=["1792", "1799", "1815"],
        misconceptions=["confusion", None, None],
        target_error="confusion",
        target_why="1792, c'est la République.",
    )
    material = unit.material.model_copy(update={"questions": [*unit.material.questions, question]})
    unit = unit.model_copy(update={"material": material})
    mcq = registry.get(ActivityCode.MCQ)
    built = [mcq.build([unit], 1, random.Random(seed)) for seed in range(40)]
    chosen = [b for b in built if b.payload["prompt"] == question.stem]
    others = len(unit.material.questions_of(1)) - 1
    assert len(chosen) > len(built) / (others + 1)  # plus souvent qu'au hasard
    assert str(chosen[0].solution["explanation"]).startswith(
        "Attention au piège : 1792, c'est la République."
    )
