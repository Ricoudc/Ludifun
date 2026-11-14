"""Jeux d'apprentissage de novembre 2026 (§5.98) : chacun se construit à partir du matériel déjà
contrôlé, sans rien inventer, et se corrige juste, à moitié ou faux."""

import random

import pytest

from app.domain.activities.base import ActivityCode, BuiltActivity
from app.domain.activities.new_games import REASONS, Stairs
from app.domain.activities.registry import ActivityRegistry
from app.domain.errors import ErrorType
from app.domain.knowledge import Grade, KnowledgeUnit, Subject
from app.domain.simulated_pupil import respond
from tests.domain.conftest import LESSON_FILES, load_lesson
from tests.domain.test_alignment import unit as math_unit
from tests.domain.test_word_games import unit as french_unit


def history_units() -> list[KnowledgeUnit]:
    return list(load_lesson(next(f for f in LESSON_FILES if "history" in f)).units.values())


def with_traps(unit: KnowledgeUnit) -> KnowledgeUnit:
    """Une notion dont les mauvaises réponses disent l'erreur qu'elles révèlent (prompt v11)."""
    questions = [
        q.model_copy(update={"misconceptions": ["confusion", "knowledge", "reading"]})
        for q in unit.material.questions
    ]
    return unit.model_copy(update={"material": unit.material.model_copy(update={"questions": questions})})


def learning_games(registry: ActivityRegistry) -> list[BuiltActivity]:
    """Un exemple des jeux qu'aucune leçon de référence ne permet à elle seule."""
    built = []
    trapped = with_traps(history_units()[0])
    built.append(registry.get(ActivityCode.CHECK_LUDI).build([trapped], 2, random.Random(3)))
    young = french_unit("Les syllabes", grade=Grade.CP)
    for difficulty in (1, 2):
        built.append(registry.get(ActivityCode.WORD_TRAIN).build([young], difficulty, random.Random(3)))
    counting = math_unit("Comparer des nombres jusqu'à 20").model_copy(update={"grade": Grade.CP})
    for difficulty in (1, 2):
        built.append(registry.get(ActivityCode.COUNT_TOUCH).build([counting], difficulty, random.Random(3)))
    return built


def grade(registry: ActivityRegistry, activity: BuiltActivity, response: dict[str, object]) -> float:
    return registry.for_activity(activity).grade(activity, response).score


def test_spot_the_error_replaces_one_word_and_half_credit_for_finding_it(registry: ActivityRegistry) -> None:
    game = registry.get(ActivityCode.SPOT_ERROR)
    unit = next(u for u in history_units() if game.accepts(u))
    activity = game.build([unit], 2, random.Random(1))
    words = {w["id"]: w["text"] for w in activity.payload["words"]}
    sentence = activity.solution["display"]
    assert " ".join(words.values()) != sentence  # un mot a été remplacé
    error = activity.solution["error_id"]
    assert words[error] not in sentence  # une mauvaise réponse, absente de la phrase vraie
    wrong_fix = next(
        c["id"] for c in activity.payload["choices"] if c["id"] != activity.solution["choice_id"]
    )
    assert grade(registry, activity, {"word_id": error, "choice_id": activity.solution["choice_id"]}) == 1.0
    assert grade(registry, activity, {"word_id": error, "choice_id": wrong_fix}) == 0.5


def test_fading_hides_more_words_at_each_difficulty(registry: ActivityRegistry) -> None:
    game = registry.get(ActivityCode.FADING)
    unit = next(u for u in history_units() if game.accepts(u))
    hidden = [len(game.build([unit], d, random.Random(2)).payload["hidden"]) for d in (2, 3)]
    assert hidden[0] == 2 and hidden[0] < hidden[1]
    assert not game.can_build([unit], 1)  # une notion fragile : la réponse sous les yeux d'abord
    activity = game.build([unit], 2, random.Random(2))
    first, second = (str(i) for i in activity.payload["hidden"])
    answers = [[int(first), activity.solution["expected"][first].upper()], [int(second), "faux"]]
    assert grade(registry, activity, {"answers": answers}) == 0.5  # majuscules sans importance


def test_check_ludi_needs_the_kind_of_error(registry: ActivityRegistry) -> None:
    game = registry.get(ActivityCode.CHECK_LUDI)
    plain = history_units()[0]
    assert not game.accepts(plain)  # sans le type d'erreur des mauvaises réponses : pas de jeu
    unit = with_traps(plain)
    wrong_ludi = next(
        a
        for seed in range(20)
        if not (a := game.build([unit], 2, random.Random(seed))).solution["ludi_right"]
    )
    reasons = {r["text"] for r in wrong_ludi.payload["reasons"]}
    assert len(reasons) == 3 and reasons <= set(REASONS.values())
    other = next(
        r["id"] for r in wrong_ludi.payload["reasons"] if r["id"] != wrong_ludi.solution["reason_id"]
    )
    assert grade(registry, wrong_ludi, {"right": False, "reason_id": other}) == 0.5
    assert grade(registry, wrong_ludi, {"right": False, "reason_id": wrong_ludi.solution["reason_id"]}) == 1.0


def test_who_am_i_hides_the_name_in_its_clues(registry: ActivityRegistry) -> None:
    game = registry.get(ActivityCode.WHO_AM_I)
    units = history_units()
    group = next(units[i : i + 3] for i in range(len(units) - 2) if game.can_build(units[i : i + 3], 2))
    activity = game.build(group, 2, random.Random(4))
    label = group[0].item.label.lower()
    assert 2 <= len(activity.payload["clues"]) <= 3
    assert all(label not in clue.lower() for clue in activity.payload["clues"])
    right = activity.solution["choice_id"]
    assert grade(registry, activity, {"choice_id": right, "clues_used": 1}) == 1.0
    assert grade(registry, activity, {"choice_id": right, "clues_used": 3}) == 0.8
    known = respond(activity, lambda key: key == group[0].id)
    assert grade(registry, activity, known) == 1.0


def test_stairs_go_from_easiest_to_hardest(registry: ActivityRegistry) -> None:
    every = [u for name in LESSON_FILES for u in load_lesson(name).units.values()]
    unit = next(u for u in every if Stairs().accepts(u))
    activity = registry.get(ActivityCode.STAIRS).build([unit], 2, random.Random(5))
    stems = [s["prompt"] for s in activity.payload["steps"]]
    difficulty = {q.stem: q.difficulty for q in unit.material.questions}
    assert [difficulty[s] for s in stems] == sorted(difficulty[s] for s in stems)
    first_right = [[activity.payload["steps"][0]["id"], activity.solution["right"]["m1"]]]
    graded = registry.for_activity(activity).grade(activity, {"answers": first_right})
    assert "marche atteinte : 1/" in graded.correct_answer


def test_young_games_stay_with_young_children(registry: ActivityRegistry) -> None:
    train, count = registry.get(ActivityCode.WORD_TRAIN), registry.get(ActivityCode.COUNT_TOUCH)
    assert train.accepts(french_unit("Les syllabes", grade=Grade.CP))
    assert not train.accepts(french_unit("Les syllabes", grade=Grade.CM2))
    young_math = math_unit("Comparer des nombres jusqu'à 20").model_copy(update={"grade": Grade.CE1})
    assert count.accepts(young_math)
    assert not count.accepts(young_math.model_copy(update={"grade": Grade.CM1}))
    assert not count.accepts(young_math.model_copy(update={"subject": Subject.FRENCH}))
    activity = count.build([young_math], 1, random.Random(6))
    target = activity.payload["target"]
    assert 3 <= target <= 10 and len(activity.payload["objects"]) > target
    selected = activity.payload["objects"][: target - 1]
    graded = count.grade(activity, {"selected": selected})
    assert graded.score == 0.0 and graded.errors[young_math.id] is ErrorType.CALCULATION


@pytest.mark.parametrize("code", sorted(ActivityCode.__members__.values()))
def test_every_learning_game_is_graded_right_and_wrong(
    registry: ActivityRegistry, code: ActivityCode
) -> None:
    examples = [a for a in learning_games(registry) if a.type == code]
    for activity in examples:
        assert grade(registry, activity, respond(activity, lambda _: True)) == 1.0
        assert grade(registry, activity, respond(activity, lambda _: False)) == 0.0
