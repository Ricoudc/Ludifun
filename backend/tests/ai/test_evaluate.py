from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.ai.ocr.vision_llm import VisionLLMOcr
from app.ai.ports import PageImage
from app.ai.pricing import run_cost
from app.ai.providers.fake import DEMO_LESSON, FakeProvider, LessonScript
from app.ai.schemas import OcrPage, OcrResult, UncertainOut
from app.domain.activities.registry import default_registry
from app.domain.knowledge import Grade, Subject
from app.services.lesson_pipeline import LessonPipeline
from app.tools.evaluate import (
    Expected,
    ExpectedNotion,
    load_corpus,
    main,
    match_notion,
    metrics,
    render_report,
    resume_after_review,
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
        ("gpt-5-mini-2026-01-01", 0.5 + 4.0),  # gpt-5-mini avant gpt-5
        ("gpt-5-2026-01-01", 2.0 + 15.0),
        ("models/gemini-2.5-flash", 0.5 + 4.0),
        ("mistral-medium-latest", 1.0 + 5.0),
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
    assert measures.count("| ✅ |") == 9  # toutes les mesures à seuil sont atteintes…
    # …sauf les aides : les leçons de référence de l'IA factice datent d'avant l'étape 14.
    assert [line.split(" |")[0] for line in measures.splitlines() if "❌" in line] == [
        "| Notions avec indice et rappel"
    ]
    assert "| Noms personnels dans le texte lu | — (aucune annotation) | 0 | · |" in measures
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


HISTORY = LessonScript.from_file(DEMO_LESSON).ocr_text
PHOTO = PageImage(b"\xff\xd8\xff\xe0photo", "image/jpeg")
REVOLUTION = Expected(
    subject=Subject.HISTORY,
    grade=Grade.CM1,
    support="cahier",
    essential=[ExpectedNotion(label="1789"), ExpectedNotion(label="Louis XVI")],
    personal=["Emma Martin", "école Jules Ferry"],
)


def blurry_page_with_a_name() -> OcrResult:
    """Le nom de l'élève a été recopié, et un mot bien lu reste douteux pour la lecture."""
    text = "Emma Martin\n" + HISTORY
    return OcrResult(
        pages=[
            OcrPage(
                index=0,
                quality="partial",
                text=text,
                uncertain=[
                    UncertainOut(text="Bastille", context="le peuple de Paris prend la Bastille, une prison")
                ],
            )
        ],
        language="fr",
        warnings=[],
    )


async def test_a_photo_to_check_is_still_analysed_and_measured() -> None:
    llm = FakeProvider(overrides={"ocr": blurry_page_with_a_name()})
    pipeline = LessonPipeline(VisionLLMOcr(llm), llm, default_registry())
    paused = await pipeline.run([PHOTO])
    assert paused.review and paused.analysis is None  # l'application attendrait l'enfant

    result = await resume_after_review(pipeline, paused)
    assert result.failure_reason is None and result.analysis is not None
    assert [r.stage for r in result.runs] == ["ocr", "analysis", "material", "material"]
    s = score("revolution", REVOLUTION, result, pages=1, duration_s=2.0)
    assert s.review == 1 and s.recall == 1.0
    assert s.notions == len(result.units) > 0
    assert s.personal_leaks == 1  # « Emma Martin », pas l'école
    assert s.with_help <= s.notions and s.in_skill <= s.notions

    report = render_report([s], "fake", datetime.now(UTC))
    assert "## ⚠ Noms personnels retrouvés dans le texte lu" in report
    assert "Emma Martin" not in report  # le rapport ne recopie jamais le nom
    assert "| Noms personnels dans le texte lu | 1 (1 leçon(s) annotée(s)) | 0 | ❌ |" in report
    assert "| Photos à faire vérifier (passages douteux) | 100 % | à suivre | · |" in report
