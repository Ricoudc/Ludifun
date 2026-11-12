"""« Enseigne-moi » (§83) : la réponse de Ludi à une explication, pendant que l'enfant attend.

Appel court au modèle rapide : la notion, ses points clés et la conversation, rien d'autre. En
cas d'échec, de délai dépassé ou de plafond de coût atteint, `check_reply` reconnaît les points
clés par leurs mots et Ludi relance avec une phrase du code : l'enfant n'est jamais bloqué.
"""

import asyncio
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass

from app.ai.ports import AIError, AITimeout, LLMProvider, Prompt
from app.ai.schemas import TeachOutput
from app.domain.teach import Reply, Turn, check_reply, teach_input
from app.services.lesson_pipeline import AiRunRecord

logger = logging.getLogger(__name__)
# L'application abandonne au bout de 30 s : au-delà, Ludi répond avec les phrases du code.
TIMEOUT_S = 20.0


@dataclass(frozen=True)
class LudiRun:
    reply: Reply
    run: AiRunRecord | None  # None : pas d'appel (plafond de coût atteint)


async def ludi_reply(
    llm: LLMProvider | None,
    *,
    grade: str,
    label: str,
    statement: str,
    points: Sequence[str],
    turns: Sequence[Turn],
    context: Sequence[str],
    timeout_s: float = TIMEOUT_S,
) -> LudiRun:
    """`turns` : la conversation, dont la dernière explication (sans réaction encore)."""
    current, done = turns[-1], len(turns) - 1
    if llm is None:
        return LudiRun(check_reply(None, points, current.answer, done, context), None)
    prompt = Prompt.load("teach")
    model = llm.model_for("teach")
    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            llm.structured(
                prompt=prompt,
                input=teach_input(grade, label, statement, points, turns),
                schema=TeachOutput,
            ),
            timeout_s,
        )
    except (AIError, TimeoutError) as caught:
        exc = caught if isinstance(caught, AIError) else AITimeout(f"pas de réponse en {timeout_s:g} s")
        logger.warning("« Enseigne-moi » sans IA, points clés par mots : %s", exc.status)
        latency = round((time.perf_counter() - started) * 1000)
        run = AiRunRecord(
            "teach", llm.name, model, prompt.version, None, None, latency, exc.status, [str(exc)]
        )
        return LudiRun(check_reply(None, points, current.answer, done, context), run)
    reply = check_reply(result.output.model_dump(), points, current.answer, done, context)
    usage = result.usage
    run = AiRunRecord(
        "teach",
        usage.provider,
        usage.model,
        prompt.version,
        usage.input_tokens,
        usage.output_tokens,
        usage.latency_ms,
        "ok",
        list(reply.warnings),
    )
    return LudiRun(reply, run)
