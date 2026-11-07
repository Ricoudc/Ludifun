"""Cloudflare Workers AI (https://developers.cloudflare.com/workers-ai/), service d'images en
ligne : aucune carte graphique sur le PC, et une part gratuite chaque jour (10 000 « neurones »,
remis à zéro à minuit UTC ; une image FLUX.1 schnell de 1024 × 1024 en 4 étapes en coûte environ
58, soit à peu près 170 images par jour). Au-delà, le service refuse jusqu'au lendemain (compte
gratuit) : aucune dépense possible sans abonnement payant.

Appelé par `POST /client/v4/accounts/{compte}/ai/run/{modèle}`, avec l'identifiant du compte
(`LUDIFUN_IMAGE_ACCOUNT_ID`) et un jeton d'API « Workers AI » (`LUDIFUN_IMAGE_API_KEY`, droits
Workers AI Read et Edit) envoyé dans
l'en-tête, jamais dans l'adresse.

Ce qui part chez Cloudflare : le prompt construit par le code (`app.domain.illustration` : scène
contrôlée, style, âge ; jamais de prénom ni de texte de leçon) et le nombre d'étapes. FLUX.1
schnell ne prend ni graine, ni taille, ni prompt négatif : « no text » reste dans le prompt.
"""

import time

import httpx

from app.ai.imagegen.common import checked_image, decode_b64
from app.ai.imagegen.ports import GeneratedImage, ImageEngineError, ImageRequest

DEFAULT_URL = "https://api.cloudflare.com/client/v4"
DEFAULT_MODEL = "@cf/black-forest-labs/flux-1-schnell"  # rapide, le moins cher en neurones
MAX_STEPS = 8  # limite du modèle ; 4 par défaut
MAX_PROMPT = 2048
TIMEOUT_S = 120.0  # une image : quelques secondes
# Codes d'erreur de Cloudflare (documentation « Workers AI errors »).
DAILY_LIMIT = 3036  # part gratuite du jour épuisée (429)
PAID_ONLY = 5035  # modèle réservé à l'offre payante (403)


class CloudflareEngine:
    name = "cloudflare"
    base_url: str | None = None  # rien sur le PC : Ollama n'a pas à être déchargé

    def __init__(
        self,
        api_token: str,
        account_id: str,
        model: str = DEFAULT_MODEL,
        api_url: str = DEFAULT_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.account_id = account_id.strip()
        self.model = model
        self._api_token = api_token
        self._client = client or httpx.AsyncClient(timeout=TIMEOUT_S)

    async def generate(self, request: ImageRequest) -> GeneratedImage:
        body = {"prompt": request.prompt[:MAX_PROMPT], "steps": max(1, min(request.steps, MAX_STEPS))}
        started = time.perf_counter()
        try:
            response = await self._client.post(
                f"{self.api_url}/accounts/{self.account_id}/ai/run/{self.model}",
                json=body,
                headers={"Authorization": f"Bearer {self._api_token}"},
            )
        except httpx.TimeoutException as exc:
            raise ImageEngineError(f"Cloudflare n'a pas répondu en {TIMEOUT_S / 60:.0f} min") from exc
        except httpx.HTTPError as exc:
            raise ImageEngineError(
                f"Cloudflare injoignable ({type(exc).__name__}) : le PC est-il connecté à Internet ?"
            ) from exc
        codes = _error_codes(response)
        if DAILY_LIMIT in codes:
            raise ImageEngineError("Cloudflare : part gratuite du jour épuisée, réessayer demain")
        if PAID_ONLY in codes:
            raise ImageEngineError(
                f"Cloudflare : « {self.model} » n'est pas dans l'offre gratuite (LUDIFUN_IMAGE_MODEL)"
            )
        if response.status_code in (401, 403):
            raise ImageEngineError(
                "Cloudflare : jeton ou compte refusé (LUDIFUN_IMAGE_API_KEY, LUDIFUN_IMAGE_ACCOUNT_ID ; "
                "le jeton doit avoir les droits Workers AI Read et Edit)"
            )
        if response.status_code == 429:
            raise ImageEngineError("Cloudflare : trop de demandes, réessayer plus tard")
        if response.status_code >= 400:
            # Le corps n'est pas recopié : il peut reprendre le prompt (journaux sans contenu).
            suffix = f" (code {codes[0]})" if codes else ""
            raise ImageEngineError(f"Cloudflare : erreur {response.status_code}{suffix}")
        try:
            result = response.json().get("result")
        except (ValueError, AttributeError) as exc:
            raise ImageEngineError("Cloudflare : réponse illisible") from exc
        data = decode_b64(result.get("image") if isinstance(result, dict) else None)
        return GeneratedImage(
            data, checked_image(data), self.name, self.model, round((time.perf_counter() - started) * 1000)
        )

    async def release(self) -> None:
        return None  # rien à libérer : le calcul se fait chez Cloudflare


def _error_codes(response: httpx.Response) -> list[int]:
    """Les codes d'erreur de la réponse (`errors: [{code, message}]`), sans leur message."""
    try:
        errors = response.json().get("errors")
    except (ValueError, AttributeError):
        return []
    if not isinstance(errors, list):
        return []
    return [e["code"] for e in errors if isinstance(e, dict) and isinstance(e.get("code"), int)]
