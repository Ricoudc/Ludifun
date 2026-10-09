import json
import random
from typing import Any

import pytest

from app.domain.activities.base import ActivityCode, BuiltActivity, CannotBuild, InvalidResponse
from app.domain.activities.registry import ActivityRegistry
from app.domain.knowledge import KnowledgeUnit
from app.domain.simulated_pupil import respond
from tests.domain.conftest import ReferenceLesson

# Clés autorisées dans le payload envoyé au téléphone : rien qui trahisse la solution.
PAYLOAD_KEYS = {
    ActivityCode.MCQ: {"prompt", "choices"},
    ActivityCode.TRUE_FALSE: {"statement"},
    ActivityCode.FILL_BLANK: {"text"},
    ActivityCode.MATCH: {"left", "right"},
    ActivityCode.SPEED_CHALLENGE: {"time_limit_s", "statements"},
    ActivityCode.FLASHCARD: {"front", "back"},
    ActivityCode.OPEN_QUESTION: {"prompt", "max_length"},
    ActivityCode.ORDER: {"prompt", "items"},
    ActivityCode.CLASSIFY: {"prompt", "categories", "items"},
    ActivityCode.TIMELINE: {"prompt", "items"},
    ActivityCode.MEMORY: {"prompt", "cards"},
    ActivityCode.MAP: {"prompt", "figure", "items"},
    ActivityCode.COLORING: {"prompt", "figure", "palette", "count"},
    ActivityCode.UNJUMBLE: {"prompt", "words"},
    ActivityCode.WORD_HUNT: {"prompt", "words"},
    ActivityCode.NUMBER_LINE: {"prompt", "task", "intervals", "labels"},  # frise d'histoire
}


def perfect_response(activity: BuiltActivity) -> dict[str, Any]:
    s = activity.solution
    match activity.type:
        case ActivityCode.MCQ:
            return {"choice_id": s["choice_id"]}
        case ActivityCode.TRUE_FALSE:
            return {"value": s["value"]}
        case ActivityCode.FILL_BLANK:
            return {"text": s["answers"][0]}
        case ActivityCode.MATCH:
            return {"pairs": [[left, right] for left, right in s["pairs"].items()]}
        case ActivityCode.SPEED_CHALLENGE:
            return {"answers": [{"id": i, "value": v} for i, v in s["answers"].items()], "elapsed_ms": 12000}
        case ActivityCode.FLASHCARD:
            return {"self_assessment": "knew"}
        case ActivityCode.OPEN_QUESTION:
            return {"text": s["model_answer"]}
    return respond(activity, lambda _: True)


def wrong_response(activity: BuiltActivity) -> dict[str, Any]:
    s = activity.solution
    match activity.type:
        case ActivityCode.MCQ:
            return {
                "choice_id": next(c["id"] for c in activity.payload["choices"] if c["id"] != s["choice_id"])
            }
        case ActivityCode.TRUE_FALSE:
            return {"value": not s["value"]}
        case ActivityCode.WORD_HUNT:  # seulement des intrus
            return {
                "selected": [w["id"] for w in activity.payload["words"] if w["id"] not in s["expected"]][:2]
            }
        case ActivityCode.CONJUGATION:
            first = activity.payload["choices"][0]["id"]
            return {"answers": [[row, first] for row in s["expected"]]}
        case ActivityCode.HOMOPHONE:
            return {"answers": [[i["id"], "x"] for i in activity.payload["items"]]}
        case ActivityCode.NUMBER_LINE | ActivityCode.FRACTION_BAR if "choice_id" in s:
            return {
                "choice_id": next(c["id"] for c in activity.payload["choices"] if c["id"] != s["choice_id"])
            }
        case ActivityCode.NUMBER_LINE:
            return {"index": s["index"] + 1}
        case ActivityCode.FRACTION_BAR:
            return {"colored": list(range(s["count"] + 1))}
        case ActivityCode.COLUMN_OP:
            return {"result": str(int(s["result"]) + 10)}
        case ActivityCode.ALIGN if "choice_id" in s:
            return {"choice_id": "non" if s["choice_id"] == "oui" else "oui"}
        case ActivityCode.ALIGN:
            return {"selected": s["expected"][1:]}
        case ActivityCode.FILL_BLANK:
            return {"text": "zzz"}
        case ActivityCode.MATCH:
            return {"pairs": []}
        case ActivityCode.SPEED_CHALLENGE:
            return {"answers": [{"id": i, "value": not v} for i, v in s["answers"].items()]}
        case ActivityCode.FLASHCARD:
            return {"self_assessment": "didnt_know"}
        case ActivityCode.OPEN_QUESTION:
            return {"text": ""}
    return respond(activity, lambda _: False)


def build_all_single(lesson: ReferenceLesson, registry: ActivityRegistry) -> list[BuiltActivity]:
    activities = []
    for unit in lesson.units.values():
        for code, difficulty in registry.single_options(unit):
            activities.append(registry.get(code).build([unit], difficulty, random.Random(7)))
    return activities


def pair_units(lesson: ReferenceLesson, registry: ActivityRegistry, count: int) -> list[KnowledgeUnit]:
    match = registry.get(ActivityCode.MATCH)
    return [u for u in lesson.units.values() if match.accepts(u)][:count]


# --------------------------------------------------------------------------- #
# Toutes les activités de toutes les leçons de référence
# --------------------------------------------------------------------------- #


def test_every_single_activity_builds_and_grades(lesson: ReferenceLesson, registry: ActivityRegistry) -> None:
    activities = build_all_single(lesson, registry)
    assert {a.type for a in activities} >= {
        ActivityCode.MCQ,
        ActivityCode.TRUE_FALSE,
        ActivityCode.FILL_BLANK,
    }
    for activity in activities:
        activity_type = registry.for_activity(activity)
        assert set(activity.payload) == PAYLOAD_KEYS[activity.type]
        json.dumps([activity.payload, activity.solution])  # stockés en JSONB

        good = activity_type.grade(activity, perfect_response(activity))
        assert (good.score, good.result) == (1.0, "correct")
        assert good.evidence == {activity.knowledge_ids[0]: 1.0}
        assert good.correct_answer
        assert good.explanation

        bad = activity_type.grade(activity, wrong_response(activity))
        assert (bad.score, bad.result) == (0.0, "incorrect")
        assert bad.evidence == {activity.knowledge_ids[0]: 0.0}
        assert set(bad.errors) == {activity.knowledge_ids[0]} and good.errors == {}


def test_multi_activities_build_on_every_lesson(lesson: ReferenceLesson, registry: ActivityRegistry) -> None:
    units = list(lesson.units.values())
    speed = registry.get(ActivityCode.SPEED_CHALLENGE)
    speed_units = [u for u in units if speed.accepts(u)][:5]
    match_units = pair_units(lesson, registry, 5)
    for activity_type, chosen, difficulty in (
        (speed, speed_units, 1),
        (registry.get("MATCH"), match_units, 2),
    ):
        activity = activity_type.build(chosen, difficulty, random.Random(3))
        assert set(activity.payload) == PAYLOAD_KEYS[activity.type]
        assert activity_type.grade(activity, perfect_response(activity)).score == 1.0
        assert activity_type.grade(activity, wrong_response(activity)).score == 0.0


def test_build_is_reproducible_with_the_same_seed(
    history: ReferenceLesson, registry: ActivityRegistry
) -> None:
    unit = history.unit("k1")
    mcq = registry.get("MCQ")
    assert mcq.build([unit], 1, random.Random(42)) == mcq.build([unit], 1, random.Random(42))


# --------------------------------------------------------------------------- #
# QCM
# --------------------------------------------------------------------------- #


def test_mcq_choices(history: ReferenceLesson, registry: ActivityRegistry) -> None:
    activity = registry.get("MCQ").build([history.unit("k1")], 1, random.Random(1))
    choices = activity.payload["choices"]
    assert [c["id"] for c in choices] == ["a", "b", "c", "d"]
    assert sorted(c["text"] for c in choices) == ["1492", "1789", "1848", "1914"]
    answer = next(c for c in choices if c["id"] == activity.solution["choice_id"])
    assert answer["text"] == "1789"
    assert activity.payload["prompt"] == "En quelle année commence la Révolution française ?"


def test_mcq_answer_position_varies(history: ReferenceLesson, registry: ActivityRegistry) -> None:
    mcq = registry.get("MCQ")
    positions = {
        mcq.build([history.unit("k1")], 1, random.Random(s)).solution["choice_id"] for s in range(40)
    }
    assert positions == {"a", "b", "c", "d"}


def test_mcq_uses_questions_of_the_requested_difficulty(
    history: ReferenceLesson, registry: ActivityRegistry
) -> None:
    mcq = registry.get("MCQ")
    unit = history.unit("k1")
    assert mcq.build([unit], 2, random.Random(0)).solution["display"] == "La Révolution française"
    assert not mcq.can_build([unit], 3)
    with pytest.raises(CannotBuild):
        mcq.build([unit], 3, random.Random(0))


@pytest.mark.parametrize(
    "response", [{}, {"choice_id": "e"}, {"choice_id": "a", "extra": 1}, {"choice_id": 3}]
)
def test_mcq_rejects_malformed_responses(
    history: ReferenceLesson, registry: ActivityRegistry, response: dict[str, Any]
) -> None:
    mcq = registry.get("MCQ")
    activity = mcq.build([history.unit("k1")], 1, random.Random(0))
    with pytest.raises(InvalidResponse):
        mcq.grade(activity, response)


def test_grading_with_the_wrong_activity_type_fails(
    history: ReferenceLesson, registry: ActivityRegistry
) -> None:
    activity = registry.get("MCQ").build([history.unit("k1")], 1, random.Random(0))
    with pytest.raises(ValueError, match="corrigée par"):
        registry.get("TRUE_FALSE").grade(activity, {"value": True})


# --------------------------------------------------------------------------- #
# Vrai / faux
# --------------------------------------------------------------------------- #


def test_true_false_draws_both_values_and_explains_false_ones(
    history: ReferenceLesson, registry: ActivityRegistry
) -> None:
    tf = registry.get("TRUE_FALSE")
    built = [tf.build([history.unit("k1")], 1, random.Random(s)) for s in range(30)]
    assert {a.solution["value"] for a in built} == {True, False}
    false_one = next(a for a in built if a.solution["value"] is False)
    assert false_one.payload["statement"] == "La Révolution française commence en 1914."
    assert false_one.solution["display"] == "Faux : La Révolution française commence en 1789."


def test_true_false_only_accepts_booleans(history: ReferenceLesson, registry: ActivityRegistry) -> None:
    tf = registry.get("TRUE_FALSE")
    activity = tf.build([history.unit("k1")], 1, random.Random(0))
    with pytest.raises(InvalidResponse):
        tf.grade(activity, {"value": "peut-être"})


# --------------------------------------------------------------------------- #
# Texte à trous
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "knowledge_id, given, score",
    [
        ("k4", "Bastille", 1.0),
        ("k4", "bastile", 1.0),  # une faute tolérée
        ("k4", "  BASTILLE. ", 1.0),
        ("k4", "Versailles", 0.0),
        ("k1", "1789", 1.0),
        ("k1", "1798", 0.0),  # les années doivent être exactes
        ("k3", "etats generaux", 1.0),  # sans accents
        ("k3", "", 0.0),
    ],
)
def test_fill_blank_tolerance(
    history: ReferenceLesson, registry: ActivityRegistry, knowledge_id: str, given: str, score: float
) -> None:
    fill = registry.get("FILL_BLANK")
    activity = fill.build([history.unit(knowledge_id)], 2, random.Random(0))
    assert "___" in activity.payload["text"]
    assert fill.grade(activity, {"text": given}).score == score


def test_fill_blank_is_not_offered_for_people(history: ReferenceLesson, registry: ActivityRegistry) -> None:
    louis = history.unit("k2")
    with_cloze = KnowledgeUnit(
        item=louis.item,
        material=louis.material.model_copy(
            update={"cloze": history.unit("k1").material.cloze},
        ),
    )
    assert not registry.get("FILL_BLANK").can_build([with_cloze], 2)  # matrice §7.2


# --------------------------------------------------------------------------- #
# Association
# --------------------------------------------------------------------------- #


def test_match_payload_and_partial_score(history: ReferenceLesson, registry: ActivityRegistry) -> None:
    match = registry.get("MATCH")
    units = pair_units(history, registry, 4)
    activity = match.build(units, 2, random.Random(5))
    assert len(activity.payload["left"]) == len(activity.payload["right"]) == 4
    assert sorted(activity.knowledge_ids) == sorted(u.id for u in units)

    pairs = list(activity.solution["pairs"].items())
    (l1, r1), (l2, r2) = pairs[0], pairs[1]
    swapped = [[l1, r2], [l2, r1], *[[left, right] for left, right in pairs[2:]]]
    grade = match.grade(activity, {"pairs": swapped})
    assert (grade.score, grade.result) == (0.5, "partial")
    knowledge_by_left = activity.solution["knowledge_by_left"]
    assert grade.evidence[knowledge_by_left[l1]] == 0.0
    assert grade.evidence[knowledge_by_left[pairs[2][0]]] == 1.0
    assert [d["correct"] for d in grade.details] == [False, False, True, True]


def test_match_right_ids_do_not_reveal_the_solution(
    history: ReferenceLesson, registry: ActivityRegistry
) -> None:
    match = registry.get("MATCH")
    units = pair_units(history, registry, 5)
    identical = sum(
        all(
            left[1:] == right[1:]
            for left, right in match.build(units, 2, random.Random(s)).solution["pairs"].items()
        )
        for s in range(20)
    )
    assert identical < 3  # l1→r1, l2→r2… ne doit pas être la règle


@pytest.mark.parametrize(
    "pairs",
    [[["l1", "r1"], ["l1", "r2"]], [["l1", "r1"], ["l2", "r1"]], [["l9", "r1"]], [["l1", "r9"]]],
)
def test_match_rejects_invalid_pairs(
    history: ReferenceLesson, registry: ActivityRegistry, pairs: list[list[str]]
) -> None:
    match = registry.get("MATCH")
    activity = match.build(pair_units(history, registry, 4), 2, random.Random(0))
    with pytest.raises(InvalidResponse):
        match.grade(activity, {"pairs": pairs})


def test_match_needs_three_distinct_pairs(history: ReferenceLesson, registry: ActivityRegistry) -> None:
    match = registry.get("MATCH")
    units = pair_units(history, registry, 3)
    assert match.can_build(units, 2)
    assert not match.can_build(units[:2], 2)
    assert not match.can_build([*units[:2], units[0]], 2)  # même notion deux fois


# --------------------------------------------------------------------------- #
# Défi rapide
# --------------------------------------------------------------------------- #


def test_speed_challenge_mixes_true_and_false(history: ReferenceLesson, registry: ActivityRegistry) -> None:
    speed = registry.get("SPEED_CHALLENGE")
    units = [history.unit(k) for k in ("k1", "k2", "k3", "k4", "k5")]
    activity = speed.build(units, 1, random.Random(9))
    assert activity.payload["time_limit_s"] == 30
    assert len(activity.payload["statements"]) == 5
    values = list(activity.solution["answers"].values())
    assert True in values and False in values
    assert len(set(activity.solution["knowledge_by_statement"].values())) == 5  # une affirmation par notion


def test_speed_challenge_unanswered_statements_count_as_errors(
    history: ReferenceLesson, registry: ActivityRegistry
) -> None:
    speed = registry.get("SPEED_CHALLENGE")
    activity = speed.build([history.unit(k) for k in ("k1", "k2", "k3", "k4", "k5")], 1, random.Random(9))
    answered = list(activity.solution["answers"].items())[:3]
    grade = speed.grade(activity, {"answers": [{"id": i, "value": v} for i, v in answered]})
    assert grade.score == pytest.approx(3 / 5)
    assert grade.result == "partial"
    assert grade.correct_answer == "3 bonne(s) réponse(s) sur 5"
    false_details = [d for d in grade.details if d["expected"] is False]
    assert all("correction" in d for d in false_details)


def test_speed_challenge_evidence_is_averaged_per_notion(
    science: ReferenceLesson, registry: ActivityRegistry
) -> None:
    speed = registry.get("SPEED_CHALLENGE")
    activity = speed.build([science.unit("k1"), science.unit("k2"), science.unit("k3")], 1, random.Random(1))
    by_knowledge: dict[str, list[str]] = {}
    for statement_id, knowledge_id in activity.solution["knowledge_by_statement"].items():
        by_knowledge.setdefault(knowledge_id, []).append(statement_id)
    k1_statements = by_knowledge["k1"]
    assert len(k1_statements) >= 2  # 3 notions pour 5 affirmations
    answers = [
        {"id": sid, "value": value if sid != k1_statements[0] else not value}
        for sid, value in activity.solution["answers"].items()
    ]
    grade = speed.grade(activity, {"answers": answers})
    assert grade.evidence["k1"] == pytest.approx(1 - 1 / len(k1_statements))
    assert grade.evidence["k2"] == 1.0


def test_speed_challenge_needs_five_statements(math: ReferenceLesson, registry: ActivityRegistry) -> None:
    speed = registry.get("SPEED_CHALLENGE")
    assert not speed.can_build([math.unit("k1"), math.unit("k2")], 1)  # 4 affirmations seulement
    assert speed.can_build([math.unit(k) for k in ("k1", "k2", "k3")], 1)


def test_speed_challenge_rejects_unknown_or_duplicate_ids(
    history: ReferenceLesson, registry: ActivityRegistry
) -> None:
    speed = registry.get("SPEED_CHALLENGE")
    activity = speed.build([history.unit(k) for k in ("k1", "k2", "k3", "k4", "k5")], 1, random.Random(0))
    for answers in (
        [{"id": "s9", "value": True}],
        [{"id": "s1", "value": True}, {"id": "s1", "value": False}],
    ):
        with pytest.raises(InvalidResponse):
            speed.grade(activity, {"answers": answers})


# --------------------------------------------------------------------------- #
# Carte mémoire
# --------------------------------------------------------------------------- #


def test_flashcard_shows_both_sides(math: ReferenceLesson, registry: ActivityRegistry) -> None:
    card = registry.get("FLASHCARD")
    activity = card.build([math.unit("k2")], 2, random.Random(0))
    assert activity.payload == {"front": "Numérateur", "back": "Le nombre de parts que l'on prend"}
    with pytest.raises(InvalidResponse):
        card.grade(activity, {"self_assessment": "bof"})
