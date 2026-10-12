"""Thème d'une notion choisi par l'IA dans une liste fermée (spécification technique §5.47) : le
code le contrôle, puis les jeux calculés s'en servent même quand le nom de la notion ne contient
pas les mots attendus."""

import copy
import random
from pathlib import Path

import pytest

from app.ai.ports import PROMPT_VERSIONS
from app.ai.schemas import KnowledgeOut
from app.domain.activities.base import ActivityCode
from app.domain.activities.registry import ActivityRegistry
from app.domain.french import HOMOPHONES
from app.domain.knowledge import FRENCH_THEMES, Grade, KnowledgeUnit, Subject, Theme, theme_fits
from app.domain.math_generator import Topic, generated_questions, topics
from app.domain.validation import validate_analysis
from tests.domain.conftest import load_lesson
from tests.domain.test_math_games import unit as math_unit
from tests.domain.test_word_games import unit as french_unit

C = ActivityCode
PROMPTS = Path(__file__).parents[2] / "app" / "ai" / "prompts"


def themed(unit: KnowledgeUnit, theme: Theme) -> KnowledgeUnit:
    return unit.model_copy(update={"item": unit.item.model_copy(update={"theme": theme})})


def test_a_theme_must_be_in_the_list_and_fit_the_subject() -> None:
    assert theme_fits("heure", Subject.MATH) is Theme.CLOCK
    assert theme_fits("conjugaison", Subject.FRENCH) is Theme.CONJUGATION
    assert theme_fits("conjugaison", Subject.MATH) is None  # autre matière
    assert theme_fits("heure", Subject.HISTORY) is None
    assert theme_fits("géométrie", Subject.MATH) is None  # hors liste
    assert theme_fits(None, Subject.MATH) is None


def test_the_prompt_lists_every_theme() -> None:
    prompt = (PROMPTS / f"analysis.{PROMPT_VERSIONS['analysis']}.md").read_text(encoding="utf-8")
    missing = [theme.value for theme in Theme if theme.value not in prompt]
    assert missing == []
    assert set(Theme) > FRENCH_THEMES


def test_an_unknown_theme_from_the_ai_does_not_break_the_analysis() -> None:
    base = {
        "id": "k1",
        "type": "rule",
        "label": "x",
        "statement": "x",
        "importance": 3,
        "attributes": {},
        "source_excerpt": "x",
        "relations": [],
    }
    assert KnowledgeOut.model_validate({**base, "theme": "géométrie"}).theme is None
    assert KnowledgeOut.model_validate({**base, "theme": "fractions"}).theme is Theme.FRACTIONS
    assert KnowledgeOut.model_validate(base).theme is None  # champ facultatif


def test_validation_keeps_a_good_theme_and_drops_a_bad_one() -> None:
    fractions = load_lesson("math_cm2_fractions.json")
    raw = copy.deepcopy(fractions.raw["analysis"])
    raw["knowledge"][0]["theme"] = "fractions"
    raw["knowledge"][1]["theme"] = "conjugaison"  # thème de français dans une leçon de maths
    raw["knowledge"][2]["theme"] = "trigonometrie"  # hors liste
    result = validate_analysis(raw, fractions.raw["ocr_text"])
    themes = [item.theme for item in result.analysis.knowledge]
    assert themes[:3] == [Theme.FRACTIONS, None, None]
    assert result.rejected == []  # les notions sont gardées, seul le thème part
    removed = [w for w in result.analysis.warnings if "thème" in w]
    assert len(removed) == 2 and removed[0].startswith("k2 : ")


@pytest.mark.parametrize(
    ("code", "notion", "theme"),
    [
        (C.CLOCK, math_unit("Le cadran", Grade.CE1), Theme.CLOCK),
        (C.MONEY, math_unit("Faire ses courses au marché", Grade.CE1), Theme.MONEY),
        (C.FRACTION_BAR, math_unit("Partager une pizza", Grade.CM1), Theme.FRACTIONS),
        (C.ALIGN, math_unit("Tracer à la règle", Grade.CE2), Theme.ALIGNMENT),
        (C.CONJUGATION, french_unit("Les verbes chanter et danser"), Theme.CONJUGATION),
        (C.HOMOPHONE, french_unit("Des mots qui se prononcent pareil"), Theme.HOMOPHONES),
        (C.ALPHA_ORDER, french_unit("Chercher un mot"), Theme.ALPHABET),
        (C.WORD_HUNT, french_unit("Le groupe nominal"), Theme.GENDER),
    ],
)
def test_the_theme_triggers_the_game(
    registry: ActivityRegistry, code: ActivityCode, notion: KnowledgeUnit, theme: Theme
) -> None:
    game = registry.get(code)
    assert not game.accepts(notion)  # les mots seuls ne suffisent pas…
    with_theme = themed(notion, theme)
    assert game.accepts(with_theme)  # … le thème, si
    for difficulty in sorted(game.difficulties):
        activity = game.build([with_theme], difficulty, random.Random(difficulty))
        assert activity.type is code


def test_a_theme_does_not_cross_subjects(registry: ActivityRegistry) -> None:
    """Un thème qui serait arrivé jusque-là malgré tout ne vaut que pour sa matière."""
    history = french_unit("La vie au Moyen Âge", subject=Subject.HISTORY)
    assert not registry.get(C.CONJUGATION).accepts(themed(history, Theme.CONJUGATION))
    assert not registry.get(C.CLOCK).accepts(themed(history, Theme.CLOCK))


def test_homophones_named_by_the_theme_use_the_pairs_of_the_grade(registry: ActivityRegistry) -> None:
    game = registry.get(C.HOMOPHONE)
    notion = themed(french_unit("Des mots qui se prononcent pareil"), Theme.HOMOPHONES)
    activity = game.build([notion], 3, random.Random(1))
    assert {tuple(i["choices"]) for i in activity.payload["items"]} <= set(HOMOPHONES)


def test_the_theme_comes_first_in_computed_exercises() -> None:
    notion = themed(math_unit("Problèmes de la vie courante", Grade.CM1), Theme.DIVISION)
    assert topics(notion.item, Grade.CM1)[0] is Topic.DIV
    created = generated_questions(notion.item, Grade.CM1, set())
    assert created and any("÷" in q.stem or "divis" in q.stem.lower() for q in created)
    # Le thème respecte la classe : pas de Pythagore en CE1, même si l'IA le propose.
    early = themed(math_unit("Les triangles", Grade.CE1), Theme.PYTHAGORE)
    assert Topic.PYTHAGORE not in topics(early.item, Grade.CE1)
