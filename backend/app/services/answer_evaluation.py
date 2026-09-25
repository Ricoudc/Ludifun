"""Correction d'une réponse rédigée par l'IA (spécification technique §6.4).

Appel court pendant la séance : la question, ses points clés, la réponse modèle et la réponse
de l'enfant, rien d'autre (ni l'historique, ni la leçon entière). En cas d'échec, de sortie
douteuse ou de confiance trop faible, `evaluate` renvoie None et la question est corrigée par
ses mots clés (`OpenQuestionActivity.grade`) : l'enfant n'est jamais bloqué.
"""

import asyncio
import logging
import time
from dataclasses import dataclass

from app.ai.ports import AIError, AITimeout, LLMProvider, Prompt
from app.ai.schemas import EvaluationOutput
from app.domain.activities.open_question import OpenEvaluation
from app.services.lesson_pipeline import AiRunRecord

logger = logging.getLogger(__name__)
MIN_CONFIDENCE = 0.4
FEEDBACK_MAX_LENGTH = 400
# L'enfant attend devant l'écran, et l'application abandonne au bout de 30 s : au-delà, on
# corrige par les mots clés (une IA locale lente peut mettre plusieurs minutes).
TIMEOUT_S = 20.0


@dataclass(frozen=True)
class EvaluationRun:
    evaluation: OpenEvaluation | None
    run: AiRunRecord


def evaluation_input(prompt: str, key_points: list[str], model_answer: str, answer: str, grade: str) -> str:
    points = "\n".join(f"- {p}" for p in key_points)
    # Les chevrons de la réponse sont neutralisés : l'enfant ne peut pas fermer la balise.
    safe = answer.replace("<", "‹").replace(">", "›")
    return (
        f"Classe de l'élève : {grade}\n\n"
        f"Question : {prompt}\n\n"
        f"<points_cles>\n{points}\n</points_cles>\n\n"
        f"Réponse modèle : {model_answer}\n\n"
        f"<reponse_eleve>\n{safe}\n</reponse_eleve>\n\n"
        "Corrige la réponse de l'élève."
    )


def to_evaluation(output: EvaluationOutput, key_points: list[str]) -> OpenEvaluation | None:
    """Garde-fous sur la sortie : points clés connus seulement, score borné, retour court."""
    feedback = output.feedback.strip()
    if not feedback or len(feedback) > FEEDBACK_MAX_LENGTH or output.confidence < MIN_CONFIDENCE:
        return None
    found = [p for p in key_points if p in output.key_points_found]
    return OpenEvaluation(
        score=min(1.0, max(0.0, output.score)),
        key_points_found=found,
        error_type=output.error_type,
        feedback=feedback,
        confidence=output.confidence,
    )


class AnswerEvaluator:
    def __init__(self, llm: LLMProvider, timeout_s: float | None = None) -> None:
        self.llm = llm
        self.prompt = Prompt.load("evaluation")
        self.timeout_s = TIMEOUT_S if timeout_s is None else timeout_s

    async def evaluate(
        self, *, prompt: str, key_points: list[str], model_answer: str, answer: str, grade: str
    ) -> EvaluationRun:
        model = self.llm.model_for("evaluation")
        started = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                self.llm.structured(
                    prompt=self.prompt,
                    input=evaluation_input(prompt, key_points, model_answer, answer, grade),
                    schema=EvaluationOutput,
                ),
                self.timeout_s,
            )
        except (AIError, TimeoutError) as caught:
            late = AITimeout(f"pas de réponse en {self.timeout_s:g} s")
            exc = caught if isinstance(caught, AIError) else late
            latency = round((time.perf_counter() - started) * 1000)
            logger.warning("Correction IA impossible, correction par mots clés : %s", exc.status)
            run = AiRunRecord(
                "evaluation",
                self.llm.name,
                model,
                self.prompt.version,
                None,
                None,
                latency,
                exc.status,
                [str(exc)],
            )
            return EvaluationRun(None, run)
        usage = result.usage
        evaluation = to_evaluation(result.output, key_points)
        run = AiRunRecord(
            "evaluation",
            usage.provider,
            usage.model,
            self.prompt.version,
            usage.input_tokens,
            usage.output_tokens,
            usage.latency_ms,
            "ok" if evaluation else "invalid_output",
            [] if evaluation else ["sortie écartée (retour vide ou trop long, ou confiance trop faible)"],
        )
        return EvaluationRun(evaluation, run)
