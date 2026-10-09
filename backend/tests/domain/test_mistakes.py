"""Erreurs lisibles par le parent : chaque jeu raté se décrit (question, réponse, bonne réponse)."""

import random

from app.domain.activities.base import ActivityCode, BuiltActivity, CannotBuild
from app.domain.activities.registry import ActivityRegistry
from app.domain.mistakes import describe
from tests.domain.conftest import LESSON_FILES, load_lesson
from tests.domain.test_activities import wrong_response
from tests.domain.test_alignment import unit as alignment_unit
from tests.domain.test_spelling_games import spelling_unit


def every_activity(registry: ActivityRegistry) -> list[BuiltActivity]:
    built = []
    for name in LESSON_FILES:
        units = list(load_lesson(name).units.values())
        for game in registry.all():
            for difficulty in sorted(game.difficulties):
                usable = [u for u in units if game.accepts(u)]
                groups = (
                    [usable[: game.max_units], usable[1 : game.max_units + 1]]
                    if game.multi_knowledge
                    else [[u] for u in usable]
                )
                for group in groups:
                    try:
                        built.append(game.build(group, difficulty, random.Random(3)))
                    except CannotBuild:
                        continue
    # Listes de mots à savoir écrire (aucune leçon de référence n'en a).
    unit = spelling_unit("chevaux")
    for code in (ActivityCode.WORD_FLASH, ActivityCode.SCRAMBLE, ActivityCode.DICTATION):
        game = registry.get(code)
        built.append(game.build([unit], min(game.difficulties), random.Random(3)))
    # Points alignés : une notion de maths sur l'alignement (aucune leçon de référence n'en a).
    alignment = registry.get(ActivityCode.ALIGN)
    for difficulty in sorted(alignment.difficulties):
        built.append(alignment.build([alignment_unit()], difficulty, random.Random(3)))
    # Jeux en images : seulement avec des images validées par le parent (étape 28).
    units = list(load_lesson(LESSON_FILES[0]).units.values())[:3]
    with_pictures = [u.model_copy(update={"picture": f"/img/{i}"}) for i, u in enumerate(units)]
    for code in (ActivityCode.PICTURE_MATCH, ActivityCode.PICTURE_FIND):
        game = registry.get(code)
        built.append(game.build(with_pictures, min(game.difficulties), random.Random(3)))
    return built


def test_every_game_describes_a_wrong_answer(registry: ActivityRegistry) -> None:
    activities = every_activity(registry)
    assert {a.type for a in activities} == set(ActivityCode)
    for activity in activities:
        mistake = describe(registry, activity, wrong_response(activity))
        assert mistake is not None, activity.type
        assert mistake.given and mistake.expected, activity.type
        assert "{" not in mistake.given + mistake.expected  # pas de structure brute montrée


def test_the_mcq_shows_the_chosen_text(registry: ActivityRegistry) -> None:
    activity = next(a for a in every_activity(registry) if a.type == ActivityCode.MCQ)
    mistake = describe(registry, activity, wrong_response(activity))
    assert mistake is not None
    choices = {c["id"]: c["text"] for c in activity.payload["choices"]}
    assert mistake.question == activity.payload["prompt"]
    assert mistake.given == choices[wrong_response(activity)["choice_id"]]
    assert mistake.expected == activity.solution["display"]


def test_an_unreadable_answer_is_skipped(registry: ActivityRegistry) -> None:
    activity = next(a for a in every_activity(registry) if a.type == ActivityCode.MCQ)
    assert describe(registry, activity, {"ancien": "format"}) is None
