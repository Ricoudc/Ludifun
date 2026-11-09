"""§5.77 : le jeu ne prend pas le pas sur l'apprentissage. Dans chaque séance, une part des
activités principales demande de retrouver la réponse sans la voir, quand la leçon le permet."""

import itertools
import math
from datetime import UTC, datetime

import pytest

from app.domain.activities.registry import ActivityRegistry
from app.domain.composer import Block, SessionComposer, fingerprint
from app.domain.decisions import describe
from app.domain.rules import RULES
from app.domain.understanding import cognitive_level
from tests.domain.conftest import ReferenceLesson

NOW = datetime(2026, 11, 9, tzinfo=UTC)
SHARE = RULES.session.min_recall_share


@pytest.mark.parametrize("seed", range(6))
def test_every_session_asks_to_recall(lesson: ReferenceLesson, registry: ActivityRegistry, seed: int) -> None:
    units = list(lesson.units.values())
    plan = SessionComposer(registry, daily_game=False).compose(units, {}, NOW, seed=seed)
    main = [i for i in plan.items if i.block in (Block.WARMUP, Block.CORE)]
    recall = [i for i in main if cognitive_level(i.activity.type, i.activity.difficulty) >= 2]
    possible = any(cognitive_level(code, d) >= 2 for u in units for code, d in registry.single_options(u))
    if possible:
        # Arrondi au-dessus, sauf quand les formats « se rappeler » de la leçon sont épuisés.
        guarded = [i for i in main if i.reason["facts"].get("recall_guard")]
        assert len(recall) >= math.ceil(SHARE * len(main)) or guarded, lesson.name
    # Le garde-fou ne casse aucune règle de la séance : jamais deux formats à la suite, aucune
    # question reposée à sa place, la raison le dit.
    types = [i.activity.type for i in plan.items]
    assert all(a != b for a, b in itertools.pairwise(types))
    others = [fingerprint(i.activity) for i in plan.items if not i.reason["facts"].get("recall_guard")]
    for item in plan.items:
        if item.reason["facts"].get("recall_guard"):
            assert fingerprint(item.activity) not in others  # une question neuve, jamais reposée
    for item in plan.items:
        if item.reason["facts"].get("recall_guard"):
            text = describe(item.reason)
            assert text is not None and "pas seulement jouer" in text
            assert item.block is Block.CORE


def test_the_guard_replaces_recognition_in_the_core(
    history: ReferenceLesson, registry: ActivityRegistry
) -> None:
    units = list(history.units.values())
    guarded = [
        i
        for seed in range(30)
        for i in SessionComposer(registry, daily_game=False).compose(units, {}, NOW, seed=seed).items
        if i.reason["facts"].get("recall_guard")
    ]
    # Sur la Révolution (beaucoup de QCM et de vrai/faux), le garde-fou sert au moins une fois.
    assert guarded and all(cognitive_level(i.activity.type, i.activity.difficulty) >= 2 for i in guarded)


@pytest.mark.parametrize("seed", range(10))
def test_two_notions_never_get_the_same_question(
    lesson: ReferenceLesson, registry: ActivityRegistry, seed: int
) -> None:
    """Deux événements de 1789 ne reçoivent plus la même « droite graduée » dans une séance."""
    plan = SessionComposer(registry).compose(list(lesson.units.values()), {}, NOW, seed=seed)
    asked = [fingerprint(i.activity) for i in plan.items if not i.reason["facts"].get("repeat")]
    assert len(asked) == len(set(asked)), lesson.name
