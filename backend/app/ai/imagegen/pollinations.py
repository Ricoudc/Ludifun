"""Pollinations (https://pollinations.ai), service d'images en ligne : aucune carte graphique sur le
PC. Appelé par `GET /image/{prompt}` (https://gen.pollinations.ai), clé secrète `sk_…` créée sur
https://enter.pollinations.ai/keys, envoyée dans l'en-tête (jamais dans l'adresse).

Ce qui part chez Pollinations : le prompt construit par le code (`app.domain.illustration` :
scène contrôlée, style, âge ; jamais de prénom ni de texte de leçon), la taille et la graine.
Les filtres « sexual » et « violence » du service sont demandés en plus des contrôles du code.
Le prompt négatif n'existe pas sur cette route : « no text » reste dans le prompt lui-même.
"""

import time
from urllib.parse import quote

import httpx

from app.ai.imagegen.common import checked_image
from app.ai.imagegen.ports import GeneratedImage, ImageEngineError, ImageRequest

DEFAULT_URL = "https://gen.pollinations.ai"
DEFAULT_MODEL = "black-forest-labs/flux.1-schnell"  # rapide, peu cher, respecte la graine
SAFE = "privacy,sexual,violence"
TIMEOUT_S = 180.0  # une image en ligne : quelques secondes, davantage si le service est chargé


class PollinationsEngine:
    name = "pollinations"
    base_url: str | None = None  # rien sur le PC : Ollama n'a pas à être déchargé

    def __init__(
        self, api_key: str, model: str, api_url: str = DEFAULT_URL, client: httpx.AsyncClient | None = None
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.model = model
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=TIMEOUT_S)

    async def generate(self, request: ImageRequest) -> GeneratedImage:
        params: dict[str, str | int] = {
            "model": self.model,
            "width": request.width,
            "height": request.height,
            "seed": request.seed,
            "safe": SAFE,
        }
        started = time.perf_counter()
        try:
            response = await self._client.get(
                f"{self.api_url}/image/{quote(request.prompt, safe='')}",
                params=params,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        except httpx.TimeoutException as exc:
            raise ImageEngineError(f"Pollinations n'a pas répondu en {TIMEOUT_S / 60:.0f} min") from exc
        except httpx.HTTPError as exc:
            raise ImageEngineError(
                f"Pollinations injoignable ({type(exc).__name__}) : le PC est-il connecté à Internet ?"
            ) from exc
        if response.status_code in (401, 403):
            raise ImageEngineError(
                "Pollinations : clé refusée (LUDIFUN_IMAGE_API_KEY ; une clé secrète sk_… est conseillée)"
            )
        if response.status_code == 402:
            raise ImageEngineError("Pollinations : crédit épuisé sur le compte")
        if response.status_code == 429:
            raise ImageEngineError("Pollinations : trop de demandes, réessayer plus tard")
        if response.status_code >= 400:
            # Le corps n'est pas recopié : il peut reprendre le prompt (journaux sans contenu).
            raise ImageEngineError(f"Pollinations : erreur {response.status_code}")
        data = response.content
        return GeneratedImage(
            data, checked_image(data), self.name, self.model, round((time.perf_counter() - started) * 1000)
        )

    async def release(self) -> None:
        return None  # rien à libérer : le calcul se fait chez Pollinations
