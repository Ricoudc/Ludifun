"""Adaptateur Claude (API Anthropic) : sorties structurées, vision, repli automatique."""

import base64
import json
import time
from collections.abc import Mapping
from typing import Literal

import anthropic
from anthropic.types.beta import BetaContentBlockParam
from pydantic import BaseModel, ValidationError

from app.ai.ports import AIError, AIInvalidOutput, AIRefused, LLMResult, PageImage, Prompt, Stage, Usage

Effort = Literal["low", "medium", "high", "xhigh", "max"]

# Si le modèle principal décline une requête, l'API la relance sur un modèle de repli.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_TOKENS = 16000


class ClaudeProvider:
    name = "claude"

    def __init__(
        self,
        models: Mapping[Stage, str],
        efforts: Mapping[Stage, Effort],
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self.models = dict(models)
        self.efforts = dict(efforts)
        # Identifiants lus dans l'environnement (ANTHROPIC_API_KEY ou profil `ant auth login`).
        self._client = client or anthropic.AsyncAnthropic()

    def model_for(self, stage: Stage) -> str:
        return self.models[stage]

    async def structured[T: BaseModel](
        self, *, prompt: Prompt, input: str, schema: type[T], images: tuple[PageImage, ...] = ()
    ) -> LLMResult[T]:
        content: list[BetaContentBlockParam] = []
        for index, image in enumerate(images):
            content.append({"type": "text", "text": f"Image {index} :"})
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image.media_type,
                        "data": base64.standard_b64encode(image.data).decode("ascii"),
                    },
                }
            )
        content.append({"type": "text", "text": input})

        model = self.models[prompt.stage]
        started = time.perf_counter()
        try:
            response = await self._client.beta.messages.parse(
                model=model,
                max_tokens=MAX_TOKENS,
                # Prompt système fixe et mis en cache ; le contenu variable est dans le message.
                system=[{"type": "text", "text": prompt.text, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": content}],
                thinking={"type": "adaptive"},
                output_config={"effort": self.efforts[prompt.stage]},
                output_format=schema,
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except (ValidationError, json.JSONDecodeError) as exc:
            raise AIInvalidOutput(f"réponse hors schéma : {exc}") from exc
        except anthropic.APIStatusError as exc:
            raise AIError(f"API {exc.status_code} : {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise AIError(f"connexion impossible : {exc}") from exc
        latency_ms = round((time.perf_counter() - started) * 1000)

        if response.stop_reason == "refusal":
            raise AIRefused("le modèle a refusé la demande")
        if response.stop_reason == "max_tokens":
            raise AIInvalidOutput("réponse tronquée (max_tokens)")
        output = response.parsed_output
        if output is None:
            raise AIInvalidOutput("aucune sortie structurée")
        usage = Usage(
            provider=self.name,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=latency_ms,
        )
        return LLMResult(output, usage)
