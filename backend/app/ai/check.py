"""« Tester » dans l'espace parent : le service répond-il, la clé est-elle acceptée, quels
modèles propose-t-il ? Une simple liste des modèles : rien n'est facturé."""

from dataclasses import dataclass, field

import httpx

from app.ai.factory import AiChoice
from app.ai.presets import PRESETS
from app.config import Settings

TIMEOUT_S = 15.0
ANTHROPIC_MODELS = "https://api.anthropic.com/v1/models"


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    message: str
    models: list[str] = field(default_factory=list)


def _refused(status: int) -> str | None:
    if status in (401, 403):
        return "Clé refusée : vérifiez-la (et le crédit du compte)."
    if status == 404:
        return "Adresse inconnue : vérifiez l'adresse de l'API."
    if status >= 400:
        return f"Le service répond une erreur ({status})."
    return None


async def check(choice: AiChoice, settings: Settings, client: httpx.AsyncClient | None = None) -> CheckResult:
    if choice.provider == "fake":
        return CheckResult(True, "IA de démonstration : toute photo devient une leçon d'exemple.")
    own_client = client is None
    http = client or httpx.AsyncClient(timeout=TIMEOUT_S)
    try:
        return await _check(choice, settings, http)
    except httpx.HTTPError as exc:
        where = "Ollama est-il lancé sur le PC ?" if choice.provider == "ollama" else "vérifiez l'adresse."
        return CheckResult(False, f"Service injoignable ({type(exc).__name__}) : {where}")
    finally:
        if own_client:
            await http.aclose()


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
