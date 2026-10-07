"""Étape 27 : l'IA propose une scène, le code décide du prompt d'image."""

import pytest

from app.domain.illustration import NEGATIVE, Scene, build_prompt, clean_remark, validate_scene

ALT = "Un chien, un poisson et un oiseau dans un pré."


def test_a_simple_scene_is_kept() -> None:
    scene, reason = validate_scene("  A friendly dog, a fish and a bird   in a sunny meadow. ", ALT)
    assert reason == "" and scene == Scene("A friendly dog, a fish and a bird in a sunny meadow", ALT)


@pytest.mark.parametrize(
    ("description", "why"),
    [
        (None, "aucune scène"),
        ("", "aucune scène"),
        ("x" * 301, "trop longue"),
        ("A soldier with a gun on a battlefield covered in blood", "mot interdit"),
        ("A scary horror castle at night", "mot interdit"),
        ('A blackboard with the words "le pluriel" written on it', "texte"),
        ("A poster showing the numbers 7 x 8 = 56", "texte"),
        ("A shop sign that says « boulangerie »", "texte"),
    ],
)
def test_unsafe_or_textual_scenes_are_refused(description: str | None, why: str) -> None:
    scene, reason = validate_scene(description, ALT)
    assert scene is None and why in reason


def test_the_parent_needs_a_description() -> None:
    assert validate_scene("A red apple on a table", None)[0] is None
    assert validate_scene("A red apple on a table", "x" * 201)[0] is None


@pytest.mark.parametrize(("grade", "age"), [("CP", 6), ("CM1", 9), ("3e", 14), (None, 9), ("inconnu", 9)])
def test_the_prompt_is_built_by_the_code(grade: str | None, age: int) -> None:
    prompt = build_prompt(Scene("Children planting a tree", ALT), grade)
    assert prompt.prompt.startswith("Children planting a tree. children's educational book illustration")
    assert f"{age}-year-old child" in prompt.prompt and prompt.prompt.endswith("no text")
    assert prompt.negative == NEGATIVE and "text" in NEGATIVE and "weapon" in NEGATIVE
    assert (prompt.width, prompt.height) == (1024, 1024)


def test_the_parent_remark_is_data() -> None:
    assert clean_remark("  plus <simple>  ") == "plus ‹simple›"
    assert clean_remark("   ") is None and clean_remark(None) is None
    assert len(clean_remark("a" * 500) or "") == 300
