"""Vérifier une IA avant de s'en servir (espace parent) :

1. le service répond, la clé est acceptée, et quels modèles il propose (liste des modèles) ;
2. Ollama : le modèle est installé et sait lire les images ;
3. une toute petite demande réelle (« réponds {"ok": true} ») : le modèle répond, au format
   attendu. Quelques dizaines de jetons ; gratuit avec Ollama.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import httpx
from pydantic import BaseModel

from app.ai.factory import AiChoice
from app.ai.ports import AIError, LLMProvider, Prompt
from app.ai.presets import PRESETS
from app.config import Settings

TIMEOUT_S = 15.0
PROBE_TIMEOUT_S = 180.0  # Ollama charge le modèle en mémoire au premier appel
ANTHROPIC_MODELS = "https://api.anthropic.com/v1/models"


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    message: str
    models: list[str] = field(default_factory=list)


Probe = Callable[[AiChoice], Awaitable[None]]


class ProbeOut(BaseModel):
    ok: bool


PROBE_PROMPT = Prompt(
    "ocr",
    "probe",
    "Test de connexion de l'application Ludifun. Réponds seulement par l'objet {\"ok\": true}.",
)


async def probe_llm(llm: LLMProvider) -> None:
    """Demande d'essai avec le modèle principal (celui qui lit les photos)."""
    result = await llm.structured(prompt=PROBE_PROMPT, input="Réponds maintenant.", schema=ProbeOut)
    if not result.output.ok:
        raise AIError("réponse d'essai inattendue")


def _refused(status: int) -> str | None:
    if status in (401, 403):
        return "Clé refusée : vérifiez-la (et le crédit du compte)."
    if status == 404:
        return "Adresse inconnue : vérifiez l'adresse de l'API."
    if status >= 400:
        return f"Le service répond une erreur ({status})."
    return None


async def check(
    choice: AiChoice,
    settings: Settings,
    client: httpx.AsyncClient | None = None,
    probe: Probe | None = None,
) -> CheckResult:
    if choice.provider == "fake":
        return CheckResult(True, "IA de démonstration : toute photo devient une leçon d'exemple.")
    own_client = client is None
    http = client or httpx.AsyncClient(timeout=TIMEOUT_S)
    try:
        found = await _check(choice, settings, http)
    except httpx.HTTPError as exc:
        where = "Ollama est-il lancé sur le PC ?" if choice.provider == "ollama" else "vérifiez l'adresse."
        return CheckResult(False, f"Service injoignable ({type(exc).__name__}) : {where}")
    finally:
        if own_client:
            await http.aclose()
    if not found.ok or probe is None:
        return found
    return await _probe(found, choice, probe)


async def _probe(found: CheckResult, choice: AiChoice, probe: Probe) -> CheckResult:
    started = time.perf_counter()
    try:
        await asyncio.wait_for(probe(choice), PROBE_TIMEOUT_S)
    except TimeoutError:
        return CheckResult(
            False, f"{found.message} Mais la demande d'essai n'a pas abouti en 3 minutes.", found.models
        )
    except AIError as exc:
        return CheckResult(False, f"{found.message} Mais la demande d'essai a échoué : {exc}", found.models)
    seconds = time.perf_counter() - started
    return CheckResult(True, f"{found.message} Demande d'essai réussie en {seconds:.0f} s.", found.models)


async def _check(choice: AiChoice, settings: Settings, http: httpx.AsyncClient) -> CheckResult:
    preset = PRESETS[choice.provider]
    if choice.provider == "ollama":
        base = (choice.base_url or settings.ollama_base_url).rstrip("/")
        response = await http.get(f"{base}/api/tags")
        if (problem := _refused(response.status_code)) is not None:
            return CheckResult(False, problem)
        models = sorted(m["name"] for m in response.json().get("models", []))
        wanted = choice.model or preset.models["ocr"]
        if not models:
            return CheckResult(
                False, f"Ollama répond, mais aucun modèle n'est installé : « ollama pull {wanted} »."
            )
        if wanted not in models and f"{wanted}:latest" not in models:
            return CheckResult(
                False,
                f"Ollama répond, mais « {wanted} » n'est pas installé : « ollama pull {wanted} ».",
                models,
            )
        shown = await http.post(f"{base}/api/show", json={"model": wanted})
        capabilities = shown.json().get("capabilities") if shown.status_code == 200 else None
        if isinstance(capabilities, list) and "vision" not in capabilities:
            return CheckResult(
                False,
                f"« {wanted} » est installé mais ne sait pas lire les images : choisissez un modèle "
                "« vision » (par exemple qwen2.5vl:7b ou gemma3:4b).",
                models,
            )
        return CheckResult(True, f"Ollama répond, « {wanted} » est installé.", models)

    if choice.provider == "claude":
        response = await http.get(
            ANTHROPIC_MODELS,
            headers={"x-api-key": choice.api_key or "", "anthropic-version": "2023-06-01"},
        )
    else:
        base = (choice.base_url or preset.base_url or "").rstrip("/")
        response = await http.get(
            f"{base}/models", headers={"Authorization": f"Bearer {choice.api_key or ''}"}
        )
    if (problem := _refused(response.status_code)) is not None:
        return CheckResult(False, problem)
    models = sorted(str(m.get("id", "")).removeprefix("models/") for m in response.json().get("data", []))
    return CheckResult(True, f"Connexion réussie à {preset.label}.", [m for m in models if m])
