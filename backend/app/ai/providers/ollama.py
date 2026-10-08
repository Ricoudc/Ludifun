"""Adaptateur Ollama (IA installée sur le PC) : API native `/api/chat`.

L'API native plutôt que la compatibilité OpenAI : elle fixe la taille du contexte (`num_ctx`).
Par défaut, Ollama tronque sans prévenir les longues consignes, et les réponses deviennent
fantaisistes. La sortie suit le schéma JSON demandé (`format`) et reste validée ; les photos
passent en base64 (`images`). Gratuit : le modèle est journalisé `ollama/<nom>`, au prix zéro.
"""

import asyncio
import base64
import json
import logging
import re
import time
import weakref
from collections.abc import Mapping
from typing import Any, cast
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ValidationError

from app.ai.images import shrink
from app.ai.ports import AIContextFull, AIError, AIInvalidOutput, LLMResult, PageImage, Prompt, Stage, Usage
from app.ai.providers.openai_compatible import parse_json, schema_instructions
from app.ai.schemas import OcrPage, OcrResult

logger = logging.getLogger("ludifun.ai")

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
    "illustration": 1200,  # l'image de la leçon et jusqu'à 4 images de notions
}
# Étapes dont les consignes décrivent déjà chaque champ : le schéma n'est pas recopié en texte
# (Ollama l'impose de toute façon avec `format`). Pour le matériel, il occupait à lui seul environ
# 2 000 jetons d'un contexte de 8 192, et la réponse était tronquée.
SCHEMA_ENFORCED_ONLY: frozenset[Stage] = frozenset({"material"})
JSON_ONLY = "\n\n# Format de la réponse\nRéponds uniquement par un objet JSON valide, sans texte autour."
PLAIN_TRANSCRIPTION = (
    "\n\n# Format de la réponse\n"
    "Pour cette image, réponds uniquement par le texte transcrit, sans JSON, sans commentaire ni "
    "phrase d'introduction. Si l'image ne contient pas de texte de leçon, réponds « [illisible] »."
)
# Une seule demande à la fois par serveur Ollama : sur une carte graphique de 8 Go, deux lectures
# de photo en même temps (deux leçons envoyées coup sur coup) font s'arrêter le moteur.
_BUSY: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, asyncio.Lock]]" = (
    weakref.WeakKeyDictionary()
)


def gpu_lock(base_url: str) -> asyncio.Lock:
    """Une demande à la fois par ordinateur (pas seulement par adresse) : Ollama et le moteur
    d'images (étape 27) partagent la même carte graphique, ils ne calculent jamais ensemble."""
    locks = _BUSY.setdefault(asyncio.get_running_loop(), {})
    host = urlsplit(base_url).hostname or base_url
    return locks.setdefault(_same_machine(host), asyncio.Lock())


def _same_machine(host: str) -> str:
    """Docker joint le PC par host.docker.internal : c'est la même carte que localhost."""
    return "localhost" if host in ("host.docker.internal", "127.0.0.1", "::1") else host


_lock = gpu_lock


async def unload_models(base_url: str, client: httpx.AsyncClient | None = None) -> list[str]:
    """Décharge les modèles chargés (`keep_alive: 0`) pour libérer la carte avant une image.
    Renvoie les modèles déchargés ; une erreur n'empêche rien (Ollama peut être éteint)."""
    own = client is None
    http = client or httpx.AsyncClient(timeout=30)
    base = base_url.rstrip("/")
    unloaded: list[str] = []
    try:
        loaded = (await http.get(f"{base}/api/ps")).json().get("models", [])
        for entry in loaded if isinstance(loaded, list) else []:
            name = entry.get("model") or entry.get("name") if isinstance(entry, dict) else None
            if isinstance(name, str):
                await http.post(f"{base}/api/generate", json={"model": name, "keep_alive": 0})
                unloaded.append(name)
    except (httpx.HTTPError, ValueError, AttributeError):
        logger.info("Ollama : rien à décharger à %s", base)
    finally:
        if own:
            await http.aclose()
    return unloaded


class _Crashed(Exception):
    def __init__(self, error: AIError) -> None:
        self.error = error


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        models: Mapping[Stage, str],
        num_ctx: int = 8192,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.models = dict(models)
        self.num_ctx = num_ctx
        self._client = client or httpx.AsyncClient(timeout=TIMEOUT_S)
        self.last_speed: float | None = None  # jetons écrits par seconde au dernier appel

    def model_for(self, stage: Stage) -> str:
        return self.models[stage]

    async def structured[T: BaseModel](
        self, *, prompt: Prompt, input: str, schema: type[T], images: tuple[PageImage, ...] = ()
    ) -> LLMResult[T]:
        async with _lock(self.base_url):
            try:
                return await self._run(prompt, input, schema, images, MAX_IMAGE_SIDE)
            except _Crashed:
                pass
            # Nouvel essai : le moteur redémarre ; avec photos, elles sont réduites.
            try:
                return await self._run(prompt, input, schema, images, RETRY_IMAGE_SIDE)
            except _Crashed as crash:
                raise crash.error from None

    async def _run[T: BaseModel](
        self, prompt: Prompt, input: str, schema: type[T], images: tuple[PageImage, ...], side: int
    ) -> LLMResult[T]:
        if schema is OcrResult and images:
            return cast(LLMResult[T], await self._transcribe(prompt, images, side))
        return await self._chat(prompt, input, schema, images, side)

    async def _transcribe(
        self, prompt: Prompt, images: tuple[PageImage, ...], side: int
    ) -> LLMResult[OcrResult]:
        """Lecture des photos en texte libre, une page à la fois. Avec une réponse JSON imposée,
        un petit modèle de vision (qwen2.5vl:7b) se met souvent à répéter le même texte sans fin ;
        en texte libre, la même page se lit en une demi-minute (PC d'essai). Le code remet
        ensuite la transcription au format attendu. Les passages douteux (« Peux-tu vérifier ? »)
        ne sont pas demandés : seuls les « [illisible] » sont signalés, par la qualité de la page."""
        system = prompt.text + PLAIN_TRANSCRIPTION
        pages: list[OcrPage] = []
        tokens_in = tokens_out = latency = 0
        model = self.models[prompt.stage]
        for index, image in enumerate(images):
            content, data, spent = await self._request(
                prompt, system, "Recopie le texte de cette image.", None, (image,), side
            )
            text = content.strip()
            if not text or text.strip("[] ").lower() == "illisible":
                quality = "unreadable"
            elif "[illisible]" in text:
                quality = "partial"
            else:
                quality = "good"
            pages.append(OcrPage(index=index, quality=quality, text="" if quality == "unreadable" else text))
            tokens_in += data.get("prompt_eval_count") or 0
            tokens_out += data.get("eval_count") or 0
            latency += spent
        output = OcrResult(pages=pages, language="fr", warnings=[])
        return LLMResult(output, Usage(self.name, f"ollama/{model}", tokens_in, tokens_out, latency))

    async def _chat[T: BaseModel](
        self, prompt: Prompt, input: str, schema: type[T], images: tuple[PageImage, ...], side: int
    ) -> LLMResult[T]:
        model = self.models[prompt.stage]
        reminder = JSON_ONLY if prompt.stage in SCHEMA_ENFORCED_ONLY else schema_instructions(schema)
        content, data, latency_ms = await self._request(
            prompt, prompt.text + reminder, input, schema.model_json_schema(), images, side
        )
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

    async def _placement(self, model: str) -> str:
        """Pourquoi Ollama a été si lent : où est le modèle (`/api/ps`). Sur le PC d'essai, un modèle
        qui déborde de la carte graphique passe de 43 à 4 jetons/s, et une étape d'une minute et
        demie dépasse alors 15 minutes."""
        try:
            response = await self._client.get(f"{self.base_url}/api/ps", timeout=5)
            loaded = [m for m in response.json().get("models", []) if isinstance(m, dict)]
        except (httpx.HTTPError, ValueError, AttributeError):
            return "modèle trop lourd ou carte graphique non utilisée"
        current = next((m for m in loaded if m.get("name") == model or m.get("model") == model), None)
        if current is None:
            return f"le modèle {model} n'est plus chargé (Ollama a redémarré ou manque de mémoire)"
        size, vram = current.get("size") or 0, current.get("size_vram") or 0
        if self.last_speed is not None and self.last_speed < SLOW_SPEED and not (size and vram < size):
            return _slow(self.last_speed)
        if size and vram < size:
            cpu = round(100 * (size - vram) / size)
            return (
                f"le modèle tourne à {cpu} % sur le processeur, la carte graphique est pleine : "
                "fermez les jeux et vidéos, gardez « Context length » à 4k dans Ollama, puis "
                "quittez et relancez Ollama"
            )
        return (
            "le modèle est bien sur la carte graphique : la leçon est peut-être très longue ; "
            "essayez de la photographier en plusieurs fois"
        )

    async def _request(
        self,
        prompt: Prompt,
        system: str,
        input: str,
        format: dict[str, Any] | None,
        images: tuple[PageImage, ...],
        side: int,
    ) -> tuple[str, dict[str, Any], int]:
        """Un appel à /api/chat : (texte de la réponse, réponse brute, durée en ms)."""
        model = self.models[prompt.stage]
        user: dict[str, Any] = {"role": "user", "content": input}
        if images:
            user["images"] = [
                base64.standard_b64encode(shrink(image.data, side)).decode("ascii") for image in images
            ]
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "system", "content": system}, user],
            "stream": False,
            "keep_alive": KEEP_ALIVE,
            "options": {
                "num_ctx": self.num_ctx,
                "num_predict": MAX_OUTPUT[prompt.stage],
                "temperature": 0.2,
            },
        }
        if format is not None:
            body["format"] = format
        started = time.perf_counter()
        try:
            response = await self._client.post(f"{self.base_url}/api/chat", json=body)
        except httpx.TimeoutException as exc:
            cause = await self._placement(model)
            logger.warning("Ollama : %s sans réponse après %d s ; %s", prompt.stage, TIMEOUT_S, cause)
            raise AIError(
                f"Ollama n'a pas répondu en {TIMEOUT_S / 60:.0f} min ({type(exc).__name__}) : {cause}"
            ) from exc
        except httpx.HTTPError as exc:
            raise AIError(
                f"Ollama injoignable à {self.base_url} ({type(exc).__name__}) : est-il lancé sur le PC ?"
            ) from exc
        if response.status_code == 404:
            raise AIError(f"modèle Ollama « {model} » absent : lancez « ollama pull {model} » sur le PC")
        if response.status_code >= 400:
            logger.warning(
                "Ollama : %s, %d photo(s) à %d px : erreur %d après %d s",
                prompt.stage, len(images), side, response.status_code, time.perf_counter() - started,
            )  # fmt: skip
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
        logger.info("%s", _timings(prompt.stage, data, len(images), side, latency_ms))
        self.last_speed = _speed(data)
        if self.last_speed is not None and self.last_speed < SLOW_SPEED:
            logger.warning("Ollama : %s", _slow(self.last_speed))
        if data.get("done_reason") == "length":
            written = data.get("eval_count")
            if isinstance(written, int) and written >= MAX_OUTPUT[prompt.stage]:
                raise AIInvalidOutput(
                    f"l'IA a tourné en boucle : réponse coupée après {written} jetons (nouvel essai)"
                )
            read = data.get("prompt_eval_count")
            raise AIContextFull(
                f"réponse tronquée : demande de {read or '?'} jetons + réponse de {written or '?'} jetons "
                f"> contexte de {self.num_ctx} (augmentez LUDIFUN_OLLAMA_NUM_CTX)"
            )
        content = (data.get("message") or {}).get("content")
        if isinstance(content, str):
            # Modèles « qui réfléchissent » (Qwen3) : le raisonnement n'est pas la réponse.
            content = _THINKING.sub("", content)
        if not isinstance(content, str) or not content.strip():
            raise AIInvalidOutput("réponse vide")
        return content, data, latency_ms


# Raisonnement écrit avant la réponse par certains modèles (Qwen3, Qwen3-VL « thinking ») quand
# Ollama ne le sépare pas lui-même dans `message.thinking`.
_THINKING = re.compile(r"<think>.*?</think>\s*", re.DOTALL)
SLOW_SPEED = 10  # jetons/s : une carte graphique de 8 Go en fait environ 40 avec qwen2.5vl:7b


def _speed(data: Mapping[str, Any]) -> float | None:
    """Vitesse d'écriture du dernier appel, si elle est mesurable (assez de jetons écrits)."""
    written, duration = data.get("eval_count"), data.get("eval_duration")
    if not isinstance(written, int) or written < 50 or not isinstance(duration, int | float) or not duration:
        return None
    return float(written / (duration / 1e9))


def _slow(speed: float) -> str:
    """Cas réel (PC d'essai) : « 100 % GPU » affiché mais 2 jetons/s au lieu d'environ 40."""
    return (
        f"Ollama n'écrit que {speed:.0f} jeton(s)/s (environ 40 attendus sur la carte graphique) "
        "alors que le modèle est sur la carte : sa mémoire déborde dans la mémoire partagée de "
        "Windows, ou Ollama a changé de version. Redémarrez le PC, puis vérifiez avec "
        "« ollama run <modèle> --verbose » (ligne eval rate)"
    )


def _timings(stage: Stage, data: Mapping[str, Any], images: int, side: int, latency_ms: int) -> str:
    """Une ligne technique par appel, pour `Surveiller-Ludifun.bat` : où passe le temps
    (chargement du modèle, lecture de la demande, écriture), et pourquoi la réponse s'arrête.
    Aucun texte de leçon ni de réponse."""

    def seconds(key: str) -> float:
        value = data.get(key)
        return value / 1e9 if isinstance(value, int | float) else 0.0

    written = data.get("eval_count") or 0
    writing = seconds("eval_duration")
    speed = f"{written / writing:.0f} jetons/s" if writing else "?"
    photos = f", {images} photo(s) à {side} px" if images else ""
    return (
        f"Ollama : {stage}{photos} : {latency_ms / 1000:.0f} s (chargement {seconds('load_duration'):.0f} s, "
        f"lecture {data.get('prompt_eval_count') or 0} jetons en {seconds('prompt_eval_duration'):.0f} s, "
        f"écriture {written}/{MAX_OUTPUT[stage]} jetons à {speed}), fin : {data.get('done_reason') or '?'}"
    )
