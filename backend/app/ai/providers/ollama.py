"""Adaptateur Ollama (IA installée sur le PC) : API native `/api/chat`.

L'API native plutôt que la compatibilité OpenAI : elle fixe la taille du contexte (`num_ctx`).
Par défaut, Ollama tronque sans prévenir les longues consignes, et les réponses deviennent
fantaisistes. La sortie suit le schéma JSON demandé (`format`) et reste validée ; les photos
passent en base64 (`images`). Gratuit : le modèle est journalisé `ollama/<nom>`, au prix zéro.
"""

import asyncio
import base64
import json
import time
import weakref
from collections.abc import Mapping
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.ai.images import shrink
from app.ai.ports import AIContextFull, AIError, AIInvalidOutput, LLMResult, PageImage, Prompt, Stage, Usage
from app.ai.providers.openai_compatible import parse_json, schema_instructions

TIMEOUT_S = 900.0  # sur un PC sans carte graphique, une page peut prendre plusieurs minutes
# Photos réduites avant l'envoi : sur un PC, le temps de lecture suit la taille de l'image (une
# photo de 2000 px en demande plus du double). Sur une carte graphique de 8 Go, une page de cahier
# à 1344 px fait s'arrêter le moteur pendant l'analyse de l'image (PC d'essai, RX 6600) :
# 1024 px (environ 1 300 morceaux d'image au lieu de 2 300) restent lisibles pour un cahier.
MAX_IMAGE_SIDE = 1024
# Ollama qui s'arrête pendant la lecture d'une photo (« error reading llama-server response ») :
# le plus souvent, la carte graphique manque de mémoire. Un seul nouvel essai, photos réduites.
RETRY_IMAGE_SIDE = 768
# Modèle gardé en mémoire entre deux demandes : le recharger prend plus d'une minute sur un PC
# (5 minutes par défaut dans Ollama, soit un rechargement à chaque leçon ou presque).
KEEP_ALIVE = "30m"
# « health resp … connectex » : le moteur venait de s'arrêter et ne répondait pas encore.
_CRASH_MARKERS = (
    "llama-server", "llama runner", "wsarecv", "forcibly closed", "exit status", "health resp",
)  # fmt: skip
# Longueur maximale de la réponse, par étape (jetons). Un petit modèle de vision se met parfois à
# répéter le même texte sans fin : sans plafond, il remplit tout le contexte (un quart d'heure sur
# certains PC) et bloque les leçons suivantes. Réponses réelles observées : lecture 300-750 jetons,
# notions 500-1900, exercices jusqu'à 4000.
MAX_OUTPUT: dict[Stage, int] = {
    "ocr": 2500,
    "analysis": 3500,
    "material": 6000,
    "evaluation": 800,
    "sources": 1500,
}
# Une seule demande à la fois par serveur Ollama : sur une carte graphique de 8 Go, deux lectures
# de photo en même temps (deux leçons envoyées coup sur coup) font s'arrêter le moteur.
_BUSY: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, asyncio.Lock]]" = (
    weakref.WeakKeyDictionary()
)


def _lock(base_url: str) -> asyncio.Lock:
    locks = _BUSY.setdefault(asyncio.get_running_loop(), {})
    return locks.setdefault(base_url, asyncio.Lock())


class _Crashed(Exception):
    def __init__(self, error: AIError) -> None:
        self.error = error


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
        async with _lock(self.base_url):
            try:
                return await self._chat(prompt, input, schema, images, MAX_IMAGE_SIDE)
            except _Crashed:
                pass
            # Nouvel essai : le moteur redémarre ; avec photos, elles sont réduites.
            try:
                return await self._chat(prompt, input, schema, images, RETRY_IMAGE_SIDE)
            except _Crashed as crash:
                raise crash.error from None

    async def _chat[T: BaseModel](
        self, prompt: Prompt, input: str, schema: type[T], images: tuple[PageImage, ...], side: int
    ) -> LLMResult[T]:
        model = self.models[prompt.stage]
        user: dict[str, Any] = {"role": "user", "content": input}
        if images:
            user["images"] = [
                base64.standard_b64encode(shrink(image.data, side)).decode("ascii") for image in images
            ]
        body = {
            "model": model,
            "messages": [{"role": "system", "content": prompt.text + schema_instructions(schema)}, user],
            "format": schema.model_json_schema(),
            "stream": False,
            "keep_alive": KEEP_ALIVE,
            "options": {
                "num_ctx": self.num_ctx,
                "num_predict": MAX_OUTPUT[prompt.stage],
                "temperature": 0.2,
            },
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
        if response.status_code >= 400 and any(m in response.text for m in _CRASH_MARKERS):
            raise _Crashed(
                AIError(
                    f"Ollama s'est arrêté pendant le calcul (mémoire de la carte graphique "
                    f"insuffisante ?) : Ollama {response.status_code} : {response.text[:300]}"
                )
            )
        if response.status_code >= 400:
            raise AIError(f"Ollama {response.status_code} : {response.text[:300]}")
        latency_ms = round((time.perf_counter() - started) * 1000)
        data: dict[str, Any] = response.json()
        if data.get("done_reason") == "length":
            written = data.get("eval_count")
            if isinstance(written, int) and written >= MAX_OUTPUT[prompt.stage]:
                raise AIInvalidOutput(
                    f"l'IA a tourné en boucle : réponse coupée après {written} jetons (nouvel essai)"
                )
            raise AIContextFull("réponse tronquée (augmentez LUDIFUN_OLLAMA_NUM_CTX)")
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
