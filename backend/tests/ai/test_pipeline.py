import copy
from pathlib import Path
from typing import Any

import pytest

from app.ai.ocr.vision_llm import VisionLLMOcr
from app.ai.ports import AIContextFull, AIError, AIInvalidOutput, AIRefused, PageImage, Stage
from app.ai.providers.fake import (
    REFERENCE_LESSONS,
    FakeProvider,
    LessonScript,
    Override,
    analysis_output,
    material_output,
    requested_ids,
)
from app.ai.schemas import OcrPage, OcrResult
from app.domain.activities.registry import default_registry
from app.domain.knowledge import KnowledgeItem
from app.services.lesson_pipeline import (
    FailureReason,
    LessonPipeline,
    LessonStatus,
    PipelineResult,
    lesson_window,
)

PAGE = PageImage(b"\xff\xd8\xffphoto", "image/jpeg")
LESSONS = sorted(REFERENCE_LESSONS.glob("*.json"))
HISTORY = REFERENCE_LESSONS / "history_cm1_revolution.json"


async def run(
    lesson: Path = HISTORY,
    overrides: dict[Stage, Override] | None = None,
    pages: tuple[PageImage, ...] = (PAGE,),
    text: str | None = None,
    max_chars: int = 20000,
) -> tuple[PipelineResult, FakeProvider, list[LessonStatus]]:
    llm = FakeProvider(LessonScript.from_file(lesson), overrides)
    statuses: list[LessonStatus] = []

    async def on_status(status: LessonStatus) -> None:
        statuses.append(status)

    pipeline = LessonPipeline(
        VisionLLMOcr(llm), llm, default_registry(), max_chars=max_chars, on_status=on_status
    )
    return await pipeline.run(pages, text), llm, statuses


@pytest.mark.parametrize("lesson", LESSONS, ids=lambda p: p.stem)
async def test_reference_lessons_go_through_the_pipeline(lesson: Path) -> None:
    result, llm, statuses = await run(lesson)
    assert result.ready
    assert statuses == [LessonStatus.READING, LessonStatus.ANALYZING, LessonStatus.GENERATING]
    assert result.analysis is not None
    assert len(result.units) == len(result.analysis.knowledge)
    assert result.rejected == []
    # 1 OCR, 1 analyse, puis un appel d'enrichissement par lot de 5 notions.
    batches = -(-len(result.units) // 5)
    assert [r.stage for r in result.runs] == ["ocr", "analysis"] + ["material"] * batches
    assert all(r.status == "ok" for r in result.runs)
    assert [r.prompt_version for r in result.runs[:2]] == ["v2", "v7"]
    assert result.prompt_versions == {"ocr": "v2", "analysis": "v7", "material": "v9"}
    # Compétences reliées aux notions, et niveaux de compréhension exigés pour chaque notion.
    expected_skills = LessonScript.from_file(lesson).analysis["skills"]
    assert len(result.analysis.skills) == len(expected_skills) >= 2
    assert all(set(s.knowledge_ids) <= {u.id for u in result.units} for s in result.analysis.skills)
    assert set(result.required_levels) == {u.id for u in result.units}
    assert all(1 in levels for levels in result.required_levels.values())
    # Les lots demandent chacun leurs notions, sans doublon.
    asked = [k for stage, text in llm.calls if stage == "material" for k in requested_ids(text)]
    assert sorted(asked) == sorted(u.id for u in result.units)


async def test_text_input_skips_ocr() -> None:
    script = LessonScript.from_file(HISTORY)
    result, llm, _ = await run(pages=(), text=script.ocr_text)
    assert result.ready
    assert next(stage for stage, _ in llm.calls) == "analysis"


# --------------------------------------------------------------------------- #
# Échecs
# --------------------------------------------------------------------------- #


async def test_unreadable_photo() -> None:
    blank = OcrResult(
        pages=[OcrPage(index=0, quality="unreadable", text="")], language="fr", warnings=["flou"]
    )
    result, _, statuses = await run(overrides={"ocr": blank})
    assert result.failure_reason is FailureReason.UNREADABLE
    assert statuses == [LessonStatus.READING]


async def test_too_long() -> None:
    result, _, _ = await run(max_chars=100)
    assert result.failure_reason is FailureReason.TOO_LONG


async def test_not_a_lesson() -> None:
    not_lesson = analysis_output({"is_lesson": False, "lesson": None, "knowledge": [], "warnings": []})
    result, _, _ = await run(overrides={"analysis": not_lesson})
    assert result.failure_reason is FailureReason.NOT_A_LESSON


async def test_invented_notions_are_all_rejected() -> None:
    raw = copy.deepcopy(LessonScript.from_file(HISTORY).analysis)
    for item in raw["knowledge"]:
        item["source_excerpt"] = "Napoléon devient empereur en 1804"
    result, _, _ = await run(overrides={"analysis": analysis_output(raw)})
    assert result.failure_reason is FailureReason.NOT_A_LESSON
    notions = [r for r in result.rejected if r.element.startswith("analysis.k")]
    assert len(notions) == len(raw["knowledge"])
    assert all("introuvable" in r.reason for r in notions)
    # Les compétences, privées de toutes leurs notions, sont écartées elles aussi.
    assert {r.element for r in result.rejected} - {r.element for r in notions} == {
        f"analysis.{s['id']}" for s in raw["skills"]
    }


@pytest.mark.parametrize("stage", ["ocr", "analysis"])
async def test_provider_error(stage: Stage) -> None:
    result, _, _ = await run(overrides={stage: AIError("API 529 : overloaded")})
    assert result.failure_reason is FailureReason.AI_ERROR
    assert result.runs[-1].status == "error"
    assert result.runs[-1].warnings == ["API 529 : overloaded"]


async def test_refusal_is_recorded() -> None:
    result, _, _ = await run(overrides={"analysis": AIRefused("refus")})
    assert result.failure_reason is FailureReason.AI_ERROR
    assert result.runs[-1].status == "refused"


# --------------------------------------------------------------------------- #
# Relances
# --------------------------------------------------------------------------- #


async def test_invalid_analysis_is_retried_once() -> None:
    good = analysis_output(LessonScript.from_file(HISTORY).analysis)
    result, _, _ = await run(
        overrides={"analysis": lambda attempt, _: AIInvalidOutput("tronqué") if attempt == 1 else good}
    )
    assert result.ready
    assert [(r.stage, r.status) for r in result.runs[:3]] == [
        ("ocr", "ok"),
        ("analysis", "invalid_output"),
        ("analysis", "ok"),
    ]


async def test_invalid_analysis_twice_fails() -> None:
    result, llm, _ = await run(overrides={"analysis": AIInvalidOutput("tronqué")})
    assert result.failure_reason is FailureReason.AI_ERROR
    assert [stage for stage, _ in llm.calls].count("analysis") == 2


async def test_failed_material_batch_is_retried_then_recovered_by_targeted_retry() -> None:
    script = LessonScript.from_file(HISTORY)

    def flaky(attempt: int, text: str) -> Any:
        return AIError("réseau") if attempt <= 2 else material_output(script.material, requested_ids(text))

    result, llm, _ = await run(overrides={"material": flaky})
    # Les deux lots échouent (une erreur réseau n'est pas relancée ici : le SDK l'a déjà fait).
    # La relance ciblée récupère les notions d'importance ≥ 4 ; les autres sont abandonnées.
    assert result.ready
    assert {u.id for u in result.units} == {"k1", "k2", "k3", "k4", "k5"}
    assert {r.element for r in result.rejected} == {"k6", "k7", "k8"}
    material_calls = [text for stage, text in llm.calls if stage == "material"]
    assert requested_ids(material_calls[-1]) == ["k1", "k2", "k3", "k4", "k5"]


async def test_targeted_retry_for_weak_important_notion() -> None:
    script = LessonScript.from_file(HISTORY)
    poor = copy.deepcopy(script.material)
    # k2 (Louis XVI, importance 4) : énoncé qui donne la réponse, seulement une explication valide.
    poor["k2"] = {
        "questions": [
            {
                "difficulty": 1,
                "stem": "Louis XVI est-il roi ?",
                "answer": "Louis XVI",
                "distractors": ["a", "b", "c"],
            }
        ],
        "explanation": "Louis XVI est roi.",
    }

    def answer(attempt: int, text: str) -> Any:
        return material_output(poor if attempt <= 2 else script.material, requested_ids(text))

    result, llm, _ = await run(overrides={"material": answer})
    assert result.ready
    retry = [text for stage, text in llm.calls if stage == "material"][-1]
    assert requested_ids(retry) == ["k2"]
    assert "k2 · questions[0] : l'énoncé contient la réponse" in retry  # le refus est expliqué au modèle
    k2 = next(u for u in result.units if u.id == "k2")
    assert len(default_registry().single_options(k2)) >= 2


async def test_rejected_elements_are_asked_again_and_merged() -> None:
    """Une notion peu importante dont une question est refusée : relance avec la raison du
    refus ; ce qui avait passé les contrôles est gardé, la nouvelle question s'y ajoute."""
    script = LessonScript.from_file(HISTORY)
    first = copy.deepcopy(script.material)
    kept = copy.deepcopy(first["k7"]["questions"])
    bad = {
        "difficulty": 1,
        "stem": "Qui ? Robespierre",
        "answer": "Robespierre",
        "distractors": ["a", "b", "c"],
    }
    first["k7"]["questions"] = [*kept, bad]
    second = copy.deepcopy(script.material)
    new_question = {
        "difficulty": 2,
        "stem": "Quelle nouvelle question sur cette notion ?",
        "answer": "La bonne",
        "distractors": ["Une autre", "Encore une", "La dernière"],
    }
    second["k7"]["questions"] = [new_question]

    def answer(attempt: int, text: str) -> Any:
        return material_output(first if attempt <= 2 else second, requested_ids(text))

    result, llm, _ = await run(overrides={"material": answer})
    assert result.ready
    retries = [text for stage, text in llm.calls if stage == "material"][2:]
    assert [requested_ids(t) for t in retries] == [["k7"]]
    assert "l'énoncé contient la réponse" in retries[0]
    k7 = next(u for u in result.units if u.id == "k7")
    stems = [q.stem for q in k7.material.questions]
    assert stems == [q["stem"] for q in kept] + [new_question["stem"]]
    assert not [r for r in result.rejected if r.element.startswith("k7.")]


async def test_a_full_context_splits_the_batch_instead_of_failing() -> None:
    """Petit modèle local : 5 notions d'un coup dépassent sa place (réponse tronquée). Le lot est
    coupé en deux, sans relancer la même demande pour rien, et toutes les notions sont gardées."""
    script = LessonScript.from_file(HISTORY)

    def small_context(attempt: int, text: str) -> Any:
        ids = requested_ids(text)
        if len(ids) > 3:
            return AIContextFull("réponse tronquée (augmentez LUDIFUN_OLLAMA_NUM_CTX)")
        return material_output(script.material, ids)

    result, llm, _ = await run(overrides={"material": small_context})
    assert result.ready
    assert {u.id for u in result.units} == set(script.material)
    asked = [requested_ids(text) for stage, text in llm.calls if stage == "material"]
    assert asked[0] == ["k1", "k2", "k3", "k4", "k5"] and asked[1] != asked[0]  # pas de relance identique
    assert all(len(ids) <= 3 for ids in asked[1:])


async def test_a_local_model_gets_one_notion_per_call() -> None:
    """Ollama : une notion par appel, sinon l'appel dépasse la place du modèle, s'arrête après
    une dizaine de minutes, et tout est refait (PC d'essai)."""
    script = LessonScript.from_file(HISTORY)
    llm = FakeProvider(script)
    llm.name = "ollama"
    result = await LessonPipeline(VisionLLMOcr(llm), llm, default_registry()).run((PAGE,))
    assert result.ready
    asked = [requested_ids(text) for stage, text in llm.calls if stage == "material"]
    assert asked[:5] == [["k1"], ["k2"], ["k3"], ["k4"], ["k5"]]


async def test_high_rejection_rate_is_flagged() -> None:
    script = LessonScript.from_file(HISTORY)
    bad = copy.deepcopy(script.material)
    for material in bad.values():
        material["false_statements"] = list(material["true_statements"])  # toutes rejetées
        material["tip"] = "x" * 200
        material["pair"] = {"left": "x" * 50, "right": "y"}

    result, _, _ = await run(
        overrides={"material": lambda _, text: material_output(bad, requested_ids(text))}
    )
    assert result.ready
    warnings = [w for r in result.runs if r.stage == "material" for w in r.warnings]
    assert any(w.startswith("taux de rejet du matériel élevé") for w in warnings)
    assert any(r.element.startswith("k1.") for r in result.rejected)


async def test_the_analysis_is_written_for_the_class_set_by_the_parent() -> None:
    llm = FakeProvider(LessonScript.from_file(HISTORY))
    await LessonPipeline(VisionLLMOcr(llm), llm, default_registry(), pupil_grade="CE1").run((PAGE,))
    (analysis,) = [text for stage, text in llm.calls if stage == "analysis"]
    assert analysis.startswith("Classe de l'élève : CE1\nÉcriture : Élève de cycle 2")
    assert "<lecon>" in analysis


def sent_lesson(text: str) -> str:
    return text.split("<lecon>\n", 1)[1].split("\n</lecon>", 1)[0]


async def test_a_local_model_still_too_full_gets_only_the_excerpts() -> None:
    """Cas réel (PC d'essai) : même une seule notion déborde du contexte de 8 192 jetons. Au lieu
    d'abandonner, le serveur renvoie la notion avec seulement ses citations de la leçon ; le
    matériel est quand même validé sur le texte entier."""
    script = LessonScript.from_file(HISTORY)

    def full_context(attempt: int, text: str) -> Any:
        if len(sent_lesson(text)) > 200:
            return AIContextFull("réponse tronquée")
        return material_output(script.material, requested_ids(text))

    llm = FakeProvider(script, {"material": full_context})
    llm.name = "ollama"
    result = await LessonPipeline(VisionLLMOcr(llm), llm, default_registry()).run((PAGE,))
    assert result.ready
    assert {u.id for u in result.units} == set(script.material)
    sizes = [len(sent_lesson(text)) for stage, text in llm.calls if stage == "material"]
    assert sizes[0] > 200 and sizes[1] <= 200  # le second essai n'envoie que la citation


def test_lesson_window_keeps_the_passages_around_the_notions() -> None:
    script = LessonScript.from_file(HISTORY)
    items = [KnowledgeItem.model_validate(k) for k in script.analysis["knowledge"]]
    text = "Intro sans rapport. " * 400 + script.ocr_text + " Fin sans rapport." * 400
    assert lesson_window(text, items, None) == text
    window = lesson_window(text, items, 3000)
    assert len(window) <= 3000 and items[0].source_excerpt in window
    only = lesson_window(text, items[:1], 0)
    assert only == items[0].source_excerpt
