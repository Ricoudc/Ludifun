from datetime import datetime
from pathlib import Path

import pytest

from app.ai.ocr.vision_llm import VisionLLMOcr
from app.ai.pricing import run_cost
from app.ai.providers.fake import FakeProvider
from app.domain.activities.registry import default_registry
from app.services.lesson_pipeline import LessonPipeline
from app.tools.evaluate import (
    Expected,
    ExpectedNotion,
    load_corpus,
    main,
    match_notion,
    metrics,
    render_report,
    score,
)
from tests.domain.conftest import load_lesson

EXAMPLE = Path(__file__).resolve().parents[3] / "eval" / "example"


def test_match_notion() -> None:
    knowledge = load_lesson("history_cm1_revolution.json").analysis.knowledge
    assert match_notion(ExpectedNotion(label="Louis XVI"), knowledge) == "k2"
    assert match_notion(ExpectedNotion(label="les états généraux"), knowledge) == "k3"  # casse, accents
    assert match_notion(ExpectedNotion(label="Prise de la Bastile"), knowledge) == "k4"  # faute de frappe
    assert match_notion(ExpectedNotion(label="Troisième ordre", aliases=["tiers état"]), knowledge) == "k6"
    assert match_notion(ExpectedNotion(label="Napoléon Bonaparte"), knowledge) is None


@pytest.mark.parametrize(
    "model, cost",
    [
        ("claude-opus-5", 5.0 + 25.0),
        ("claude-opus-5-5", 4.0 + 20.0),  # le préfixe le plus précis l'emporte
        ("claude-sonnet-5", 2.0 + 10.0),
        ("fake", 0.0),
        ("modele-inconnu", None),
    ],
)
def test_run_cost(model: str, cost: float | None) -> None:
    assert run_cost(model, 1_000_000, 1_000_000) == cost


def test_example_corpus_end_to_end(tmp_path: Path) -> None:
    assert main([str(EXAMPLE), "--provider", "fake", "--out", str(tmp_path)]) == 0
    [run_dir] = list(tmp_path.iterdir())
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    measures = report.split("## Par leçon")[0]
    assert measures.count("| ✅ |") == 7  # toutes les mesures à seuil sont atteintes
    assert "❌" not in measures
    assert "piege_liste_de_courses | photo | 1 | ✅ not_a_lesson (piège)" in report
    for name in ("history_cm1_revolution", "math_cm2_fractions", "science_ce2_water_states"):
        assert (run_dir / f"{name}.json").exists()
        assert "══ Séance" in (run_dir / f"{name}.txt").read_text(encoding="utf-8")


async def test_missed_notions_and_failures_are_reported() -> None:
    corpus = {lesson.name: lesson for lesson in load_corpus(EXAMPLE)}
    history = corpus["history_cm1_revolution"]
    llm = FakeProvider()
    pipeline = LessonPipeline(VisionLLMOcr(llm), llm, default_registry())
    result = await pipeline.run(text=history.text)

    expected = history.expected.model_copy(
        update={"essential": [*history.expected.essential, ExpectedNotion(label="Napoléon Bonaparte")]}
    )
    good = score("histoire", expected, result, pages=2, duration_s=30.0)
    assert good.recall == pytest.approx(5 / 6)

    failed_result = await pipeline.run(text="Recette des crêpes : farine, œufs, lait.")
    expected_verb = Expected(subject="french", grade="CE1", essential=[ExpectedNotion(label="verbe")])
    failed = score("crepes", expected_verb, failed_result, pages=1, duration_s=5.0)
    assert failed.failure == "not_a_lesson" and not failed.correct_outcome

    by_name = {m.name: m for m in metrics([good, failed])}
    assert by_name["Leçons traitées correctement"].value == 50
    assert by_name["Leçons traitées correctement"].ok is False
    assert by_name["Rappel des notions indispensables"].value == pytest.approx(100 * 5 / 7)
    assert by_name["Durée photo → prête (médiane, 2 pages)"].value == 30.0

    report = render_report([good, failed], "fake", datetime(2026, 9, 23))
    assert "- **histoire** : Napoléon Bonaparte" in report
    assert "- **crepes** : verbe" in report
