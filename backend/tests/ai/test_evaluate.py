from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.ai.ocr.vision_llm import VisionLLMOcr
from app.ai.ports import PageImage
from app.ai.pricing import run_cost
from app.ai.providers.fake import DEMO_LESSON, FakeProvider, LessonScript
from app.ai.schemas import OcrPage, OcrResult, UncertainOut
from app.domain.activities.registry import default_registry
from app.domain.knowledge import Grade, KnowledgeMaterial, KnowledgeUnit, OpenQuestion, Subject
from app.services.lesson_pipeline import LessonPipeline, PipelineResult
from app.tools.evaluate import (
    Expected,
    _question_review_signature,
    ExpectedNotion,
    apply_question_review_annotations,
    load_corpus,
    main,
    match_notion,
    match_notions,
    material_counts,
    metrics,
    open_question_review,
    question_review_summary,
    render_report,
    resume_after_review,
    score,
)
from tests.domain.conftest import load_lesson
from tests.support_documents import docx, scanned_pdf

EXAMPLE = Path(__file__).resolve().parents[3] / "eval" / "example"


def test_open_question_review_export_keeps_notion_context_and_review_dimensions() -> None:
    item = load_lesson("history_cm1_revolution.json").analysis.knowledge[0]
    question = OpenQuestion(
        level=4,
        prompt="Pourquoi cette notion est-elle importante ?",
        key_points=[item.label],
        model_answer=f"Cette notion est importante : {item.label}.",
        passage=None,
    )
    unit = KnowledgeUnit(
        item=item,
        material=KnowledgeMaterial(
            knowledge_id=item.id,
            explanation=item.statement,
            open_questions=[question],
        ),
    )
    result = PipelineResult(failure_reason=None, units=[unit])

    [review] = open_question_review(result, "histoire_cm1")
    assert review["review_id"] == f"histoire_cm1:{item.id}:1"
    assert review["lesson"] == "histoire_cm1"
    assert review["knowledge_id"] == item.id
    assert review["notion"] == item.label
    assert review["prompt"] == question.prompt
    assert review["key_points"] == question.key_points
    assert review["review_status"] == "à annoter"
    assert len(review["review_signature"]) == 64
    assert "pertinence_par_rapport_a_la_notion" in review["review_dimensions"]


def test_question_review_annotations_are_reapplied_only_to_same_pedagogical_content() -> None:
    reviews: list[dict[str, Any]] = [
        {
            "review_id": "histoire:k5:1",
            "knowledge_id": "k5",
            "notion_statement": "La Révolution commence en 1789.",
            "level": 3,
            "prompt": "Explique 1789.",
            "key_points": ["date", "causes"],
            "model_answer": "La Révolution débute en 1789 pour plusieurs causes.",
            "passage": "En 1789...",
            "review_status": "à annoter",
        },
        {"review_id": "histoire:k6:1", "prompt": "Pourquoi ?", "review_status": "à annoter"},
    ]
    annotations = [
        {
            "review_id": "histoire:k5:1",
            "review_signature": _question_review_signature(reviews[0]),
            "review_status": "pertinent",
        }
    ]
    applied = apply_question_review_annotations(reviews, annotations)
    assert [row["review_status"] for row in applied] == ["pertinent", "à annoter"]
    summary = question_review_summary(applied)
    assert summary["total"] == 2 and summary["annotated"] == 1 and summary["pending"] == 1
    assert summary["pertinent_rate"] == 1.0 and summary["off_topic_rate"] == 0.0


@pytest.mark.parametrize(
    "changed_field, changed_value",
    [
        ("level", 2),
        ("key_points", ["date", "conséquences nouvelles"]),
        ("model_answer", "Une réponse modèle différente."),
        ("notion_statement", "Une notion reformulée."),
    ],
)
def test_question_review_annotation_is_invalidated_when_pedagogical_content_changes(
    changed_field: str, changed_value: Any
) -> None:
    review: dict[str, Any] = {
        "review_id": "histoire:k5:1",
        "knowledge_id": "k5",
        "notion_statement": "La Révolution commence en 1789.",
        "level": 3,
        "prompt": "Explique 1789.",
        "key_points": ["date", "causes"],
        "model_answer": "La Révolution débute en 1789 pour plusieurs causes.",
        "passage": "En 1789...",
        "review_status": "à annoter",
    }
    annotation = {
        "review_id": review["review_id"],
        "review_signature": _question_review_signature(review),
        "review_status": "pertinent",
    }
    changed_review = review | {changed_field: changed_value}

    with pytest.raises(ValueError, match="contenu pédagogique modifié"):
        apply_question_review_annotations([changed_review], [annotation])


@pytest.mark.parametrize(
    "annotations, message",
    [
        (
            [
                {"review_id": "histoire:k5:1", "review_signature": "stale", "review_status": "pertinent"},
                {"review_id": "histoire:k5:1", "review_signature": "stale", "review_status": "hors sujet"},
            ],
            "annotation en double",
        ),
        (
            [{"review_id": "histoire:k5:1", "review_signature": "stale", "review_status": "pertinent"}],
            "contenu pédagogique modifié",
        ),
        (
            [{"review_id": "histoire:inconnu:1", "review_signature": "stale", "review_status": "pertinent"}],
            "sans question correspondante",
        ),
        (
            [{"review_id": "histoire:k5:1", "review_signature": "stale", "review_status": "excellent"}],
            "label de revue invalide",
        ),
    ],
)
def test_question_review_annotations_reject_stale_or_invalid_data(
    annotations: list[dict[str, str]], message: str
) -> None:
    reviews = [{"review_id": "histoire:k5:1", "prompt": "Explique 1789.", "review_status": "à annoter"}]
    with pytest.raises(ValueError, match=message):
        apply_question_review_annotations(reviews, annotations)


def test_match_notion() -> None:
    knowledge = load_lesson("history_cm1_revolution.json").analysis.knowledge
    assert match_notion(ExpectedNotion(label="Louis XVI"), knowledge) == "k2"
    assert match_notion(ExpectedNotion(label="les états généraux"), knowledge) == "k3"  # casse, accents
    assert match_notion(ExpectedNotion(label="Prise de la Bastile"), knowledge) == "k4"  # faute de frappe
    assert match_notion(ExpectedNotion(label="Troisième ordre", aliases=["tiers état"]), knowledge) == "k6"
    assert match_notion(ExpectedNotion(label="Napoléon Bonaparte"), knowledge) is None


def test_expected_notion_recall_never_counts_one_produced_notion_twice() -> None:
    item = load_lesson("history_cm1_revolution.json").analysis.knowledge[0]
    knowledge = [
        item.model_copy(
            update={
                "id": "k1",
                "label": "Louis XVI",
                "statement": "Louis XVI était le roi de France.",
            }
        )
    ]
    expected = [
        ExpectedNotion(label="Louis XVI"),
        ExpectedNotion(label="roi de France"),
    ]

    assert match_notions(expected, knowledge) == ["k1", None]


def test_notion_matching_reassigns_a_broad_match_to_maximize_recall() -> None:
    template = load_lesson("history_cm1_revolution.json").analysis.knowledge[0]
    knowledge = [
        template.model_copy(
            update={
                "id": "k1",
                "label": "Louis XVI",
                "statement": "Le roi de France réunit les états généraux.",
            }
        ),
        template.model_copy(
            update={
                "id": "k2",
                "label": "Louis XVI",
                "statement": "Louis XVI est arrêté.",
            }
        ),
    ]
    expected = [
        ExpectedNotion(label="Louis XVI"),
        ExpectedNotion(label="roi de France"),
    ]

    assert match_notions(expected, knowledge) == ["k2", "k1"]


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
    assert measures.count("| ✅ |") == 7
    # Le corpus couvre désormais plusieurs niveaux et matières : il révèle aussi les métriques
    # pédagogiques que le fournisseur factice ne satisfait pas encore.
    assert [line.split(" |")[0] for line in measures.splitlines() if "❌" in line] == [
        "| Notions reliées à une compétence",
        "| Notions avec indice et rappel",
        "| Questions ouvertes par leçon (moyenne)",
    ]
    assert "| Noms personnels dans le texte lu | — (aucune annotation) | 0 | · |" in measures
    assert "piege_liste_de_courses | photo | 1 | ✅ not_a_lesson (piège)" in report
    for name in (
        "history_cm1_revolution",
        "math_cm2_fractions",
        "science_ce2_water_states",
        "french_cp_vowels",
        "geography_6e_continents",
        "math_3e_pythagoras",
    ):
        assert (run_dir / f"{name}.json").exists()
        assert "══ Séance" in (run_dir / f"{name}.txt").read_text(encoding="utf-8")
    assert "## Rappel des notions par matière et niveau" in report
    assert "### Par matière" in report and "### Par niveau" in report
    assert "| french | 5 | 5 | 100 % |" in report
    assert "| geography | 6 | 6 | 100 % |" in report
    assert "| history | 5 | 5 | 100 % |" in report
    assert "| math | 9 | 9 | 100 % |" in report
    assert "| science | 4 | 4 | 100 % |" in report
    assert "| 3e | 5 | 5 | 100 % |" in report
    assert "| 6e | 6 | 6 | 100 % |" in report
    assert "Notions importantes avec question ouverte" in measures
    assert "Ouvertes / notions importantes" in report


async def test_material_counts_include_open_questions_help_and_all_games() -> None:
    corpus = {lesson.name: lesson for lesson in load_corpus(EXAMPLE)}
    history = corpus["history_cm1_revolution"]
    llm = FakeProvider()
    pipeline = LessonPipeline(VisionLLMOcr(llm), llm, default_registry())
    result = await pipeline.run(text=history.text)

    expected_kept = sum(
        len(unit.material.questions)
        + len(unit.material.true_statements)
        + len(unit.material.false_statements)
        + len(unit.material.open_questions)
        + sum(
            value is not None
            for value in (
                unit.material.cloze,
                unit.material.pair,
                unit.material.flashcard,
                unit.material.tip,
                unit.material.help,
                unit.material.sorting,
                unit.material.sequence,
                unit.material.spelling,
            )
        )
        for unit in result.units
    )

    kept, rejected = material_counts(result)
    assert kept == expected_kept
    assert rejected == sum(
        1
        for rejection in result.rejected
        if "." in rejection.element and not rejection.element.startswith("analysis.")
    )


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
    important_units = [unit for unit in result.units if unit.item.importance >= 4]
    assert good.important_notions == len(important_units)
    assert good.important_with_open_question == sum(
        bool(unit.material.open_questions) for unit in important_units
    )
    by_name = {metric.name: metric for metric in metrics([good])}
    coverage = None
    if good.important_notions:
        coverage = 100 * good.important_with_open_question / good.important_notions
    assert by_name["Notions importantes avec question ouverte"].value == coverage

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
    assert "## Rappel des notions par matière et niveau" in report
    assert "| history | 5 | 6 | 83 % |" in report
    assert "| french | 0 | 1 | 0 % |" in report
    assert "| CM1 | 5 | 6 | 83 % |" in report
    assert "| CE1 | 0 | 1 | 0 % |" in report


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


def test_real_lessons_as_documents_without_annotation(tmp_path: Path) -> None:
    """Point 2 : une famille essaie ses vraies leçons en PDF ou en Word, sans rien annoter ; le
    rapport montre ce que l'application en fait (thèmes, jeux possibles, séance)."""
    lessons = tmp_path / "lecons"
    word, scan = lessons / "revolution_word", lessons / "fiche_scannee"
    word.mkdir(parents=True)
    scan.mkdir()
    text = LessonScript.from_file(DEMO_LESSON).ocr_text
    (word / "lecon.docx").write_bytes(docx(text.split("\n")))
    (scan / "fiche.pdf").write_bytes(scanned_pdf(pages=2))
    corpus = {lesson.name: lesson for lesson in load_corpus(lessons)}
    assert corpus["revolution_word"].text == text and corpus["revolution_word"].pages == []
    assert len(corpus["fiche_scannee"].pages) == 2 and corpus["fiche_scannee"].text is None
    assert corpus["revolution_word"].expected == Expected()  # pas d'annotation

    assert main([str(lessons), "--provider", "fake", "--out", str(tmp_path / "out")]) == 0
    [run_dir] = list((tmp_path / "out").iterdir())
    session = (run_dir / "revolution_word.txt").read_text(encoding="utf-8")
    assert "══ Jeux possibles par notion ══" in session and "══ Séance" in session
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "revolution_word" in report and "Matière correcte | —" in report  # rien à comparer


def test_lessons_get_their_subject_games_in_the_report(tmp_path: Path) -> None:
    """Les jeux de la matière (droite graduée, fractions…) apparaissent comme dans l'application."""
    assert (
        main([str(EXAMPLE), "--provider", "fake", "--out", str(tmp_path), "--only", "math_cm2_fractions"])
        == 0
    )
    [run_dir] = list(tmp_path.iterdir())
    games = (run_dir / "math_cm2_fractions.txt").read_text(encoding="utf-8").split("══ Jeux possibles")[1]
    assert "FRACTION_BAR" in games or "NUMBER_LINE" in games
