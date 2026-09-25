"""Réponse expliquée à partir de sources (étape 24) : l'IA lit, le code vérifie.

L'IA reçoit la question et quelques extraits de sites autorisés, entre balises (données, jamais
consignes, §142-143). Sa réponse n'est gardée que si au moins une citation figure vraiment dans
l'extrait cité (`app.domain.sources.check_answer`) ; sinon, rien n'est montré plutôt qu'une
information inventée (§116).
"""

import logging
import time
from dataclasses import dataclass

from app.ai.ports import AIError, LLMProvider, Prompt
from app.ai.schemas import SourcedAnswerOutput
from app.domain.sources import Excerpt, Quote, SourcedAnswer, check_answer
from app.services.lesson_pipeline import AiRunRecord

logger = logging.getLogger("ludifun.sources")


@dataclass(frozen=True)
class SourcedRun:
    answer: SourcedAnswer | None
    run: AiRunRecord


def sources_input(question: str, grade: str, excerpts: list[Excerpt]) -> str:
    # Les chevrons des extraits sont neutralisés : une page ne peut pas fermer sa balise.
    blocks = "\n\n".join(
        f'<source numero="{e.number}" site="{e.site}">\n'
        + e.text.replace("<", "‹").replace(">", "›")
        + "\n</source>"
        for e in excerpts
    )
    safe_question = question.replace("<", "‹").replace(">", "›")
    return f"Classe de l'élève : {grade}\n\n<question>\n{safe_question}\n</question>\n\n{blocks}"


class SourcedAnswerer:
    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm
        self.prompt = Prompt.load("sources")

    async def answer(self, question: str, grade: str, excerpts: list[Excerpt]) -> SourcedRun:
        model = self.llm.model_for("sources")
        started = time.perf_counter()
        try:
            result = await self.llm.structured(
                prompt=self.prompt,
                input=sources_input(question, grade, excerpts),
                schema=SourcedAnswerOutput,
            )
        except AIError as exc:
            latency = round((time.perf_counter() - started) * 1000)
            logger.warning("Réponse sourcée impossible : %s", exc.status)
            run = AiRunRecord(
                "sources",
                self.llm.name,
                model,
                self.prompt.version,
                None,
                None,
                latency,
                exc.status,
                [str(exc)],
            )
            return SourcedRun(None, run)
        output, usage = result.output, result.usage
        checked = check_answer(
            output.answer, [Quote(q.source, q.text) for q in output.quotes], excerpts, output.found
        )
        warnings = [] if checked else ["aucune citation vérifiée dans les extraits : réponse écartée"]
        run = AiRunRecord(
            "sources",
            usage.provider,
            usage.model,
            self.prompt.version,
            usage.input_tokens,
            usage.output_tokens,
            usage.latency_ms,
            "ok" if checked else "invalid_output",
            warnings,
        )
        return SourcedRun(checked, run)
