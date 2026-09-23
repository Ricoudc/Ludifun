import copy
from pathlib import Path
from typing import Any

import pytest

from app.ai.ocr.vision_llm import VisionLLMOcr
from app.ai.ports import AIError, AIInvalidOutput, AIRefused, PageImage, Stage
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
from app.services.lesson_pipeline import FailureReason, LessonPipeline, LessonStatus, PipelineResult

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
    assert all(r.status == "ok" and r.prompt_version == "v1" for r in result.runs)
    assert result.prompt_versions == {"ocr": "v1", "analysis": "v1", "material": "v1"}
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
    assert len(result.rejected) == len(raw["knowledge"])
    assert all("introuvable" in r.reason for r in result.rejected)


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
