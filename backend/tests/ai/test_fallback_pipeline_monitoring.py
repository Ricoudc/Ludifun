"""Contrat entre le repli fournisseur et sa journalisation dans le pipeline."""

from pydantic import BaseModel

from app.ai.ports import LLMResult, Prompt, Usage
from app.services.lesson_pipeline import AiRunRecord, LessonPipeline, PipelineResult


class Output(BaseModel):
    ok: bool


async def test_pipeline_records_the_provider_that_served_a_fallback() -> None:
    class PipelineStub:
        on_call = None

    async def fallback_response() -> LLMResult[Output]:
        return LLMResult(
            Output(ok=True),
            Usage(
                provider="gemini",
                model="gemini-flash",
                input_tokens=12,
                output_tokens=8,
                latency_ms=240,
                fallback_from="ollama : indisponible",
            ),
        )

    pipeline = PipelineStub()
    result = PipelineResult(failure_reason=None)
    response = await LessonPipeline._call(
        pipeline,  # type: ignore[arg-type]
        result,
        "analysis",
        "v8",
        "ollama",
        "ollama-model",
        fallback_response,
        retries=0,
    )

    assert response.usage.provider == "gemini"
    assert len(result.runs) == 1
    run: AiRunRecord = result.runs[0]
    assert (run.provider, run.model, run.status) == ("gemini", "gemini-flash", "ok")
    assert run.input_tokens == 12
    assert run.output_tokens == 8
    assert run.latency_ms == 240
    assert run.warnings == ["repli : ollama : indisponible"]
