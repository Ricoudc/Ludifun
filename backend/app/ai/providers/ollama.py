"""Adaptateur Ollama (IA installée sur le PC) : API native `/api/chat`.

L'API native plutôt que la compatibilité OpenAI : elle fixe la taille du contexte (`num_ctx`).
Par défaut, Ollama tronque sans prévenir les longues consignes, et les réponses deviennent
fantaisistes. La sortie suit le schéma JSON demandé (`format`) et reste validée ; les photos
passent en base64 (`images`). Gratuit : le modèle est journalisé `ollama/<nom>`, au prix zéro.
"""

import base64
import json
import time
from collections.abc import Mapping
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.ai.images import shrink
from app.ai.ports import AIError, AIInvalidOutput, LLMResult, PageImage, Prompt, Stage, Usage
from app.ai.providers.openai_compatible import parse_json, schema_instructions

TIMEOUT_S = 900.0  # sur un PC sans carte graphique, une page peut prendre plusieurs minutes
# Photos réduites avant l'envoi : sur un PC, le temps de lecture suit la taille de l'image (une
# photo de 2000 px en demande plus du double). 1344 px (48 × 28) restent lisibles pour un cahier.
MAX_IMAGE_SIDE = 1344


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        models: Mapping[Stage, str],
        num_ctx: int = 16384,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.models = dict(models)
        self.num_ctx = num_ctx
        self._client = client or httpx.AsyncClient(timeout=TIMEOUT_S)

    def model_for(self, stage: Stage) -> str:
        return self.models[stage]

    async def structured[T: BaseModel](
        self, *, prompt: Prompt, input: str, schema: type[T], images: tuple[PageImage, ...] = ()
    ) -> LLMResult[T]:
        model = self.models[prompt.stage]
        user: dict[str, Any] = {"role": "user", "content": input}
        if images:
            user["images"] = [
                base64.standard_b64encode(shrink(image.data, MAX_IMAGE_SIDE)).decode("ascii")
                for image in images
            ]
        body = {
            "model": model,
            "messages": [{"role": "system", "content": prompt.text + schema_instructions(schema)}, user],
            "format": schema.model_json_schema(),
            "stream": False,
            "options": {"num_ctx": self.num_ctx, "temperature": 0.2},
        }
        started = time.perf_counter()
        try:
            response = await self._client.post(f"{self.base_url}/api/chat", json=body)
        except httpx.TimeoutException as exc:
            raise AIError(
                f"Ollama n'a pas répondu en {TIMEOUT_S / 60:.0f} min ({type(exc).__name__}) : "
                "modèle trop lourd ou carte graphique non utilisée"
            ) from exc
        except httpx.HTTPError as exc:
            raise AIError(
                f"Ollama injoignable à {self.base_url} ({type(exc).__name__}) : est-il lancé sur le PC ?"
            ) from exc
        if response.status_code == 404:
            raise AIError(f"modèle Ollama « {model} » absent : lancez « ollama pull {model} » sur le PC")
        if response.status_code >= 400:
            raise AIError(f"Ollama {response.status_code} : {response.text[:300]}")
        latency_ms = round((time.perf_counter() - started) * 1000)
        data: dict[str, Any] = response.json()
        if data.get("done_reason") == "length":
            raise AIInvalidOutput("réponse tronquée (augmentez LUDIFUN_OLLAMA_NUM_CTX)")
        content = (data.get("message") or {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise AIInvalidOutput("réponse vide")
        try:
            output = schema.model_validate(parse_json(content))
        except (ValidationError, json.JSONDecodeError) as exc:
            raise AIInvalidOutput(f"réponse hors schéma : {exc}") from exc
        return LLMResult(
            output,
            Usage(
                provider=self.name,
                model=f"ollama/{model}",
                input_tokens=data.get("prompt_eval_count"),
                output_tokens=data.get("eval_count"),
                latency_ms=latency_ms,
            ),
        )
