"""Service d'images compatible OpenAI (`POST {adresse}/images/generations`), §5.96 : FreeLLMAPI
installé sur le PC (qui répartit entre des offres gratuites), OpenAI, ou tout service qui suit le
même format. Réglé par `LUDIFUN_IMAGE_ENGINE=openai`, `LUDIFUN_IMAGE_URL` (par exemple
`http://host.docker.internal:31415/v1`), `LUDIFUN_IMAGE_API_KEY` (envoyée dans l'en-tête, jamais
dans l'adresse) et, si le service le demande, `LUDIFUN_IMAGE_MODEL`.

Ce qui part : le prompt construit par le code (`app.domain.illustration` : scène contrôlée, style,
âge ; jamais de prénom ni de texte de leçon) et la taille. L'image revient en base64
(`b64_json`) ou par une adresse, téléchargée alors, avec la même limite de taille.
"""

import time

import httpx

from app.ai.imagegen.common import checked_image, decode_b64
from app.ai.imagegen.ports import GeneratedImage, ImageEngineError, ImageRequest

TIMEOUT_S = 180.0  # une image en ligne : quelques secondes, parfois une minute
MAX_PROMPT = 4000
MAX_BYTES = 8 * 1024 * 1024
SIZES = ("1024x1024", "1024x1536", "1536x1024")  # tailles que ces services acceptent presque tous


def size_for(width: int, height: int) -> str:
    if width > height:
        return SIZES[2]
    return SIZES[1] if height > width else SIZES[0]


class OpenAiImagesEngine:
    name = "openai"
    base_url: str | None = None  # dessin hors de la carte graphique du PC : Ollama n'est pas déchargé

    def __init__(
        self,
        api_url: str,
        api_key: str | None = None,
        model: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.model = model or "par défaut"
        self._model = model
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=TIMEOUT_S)

    async def generate(self, request: ImageRequest) -> GeneratedImage:
        body: dict[str, object] = {
            "prompt": request.prompt[:MAX_PROMPT],
            "n": 1,
            "size": size_for(request.width, request.height),
            "response_format": "b64_json",
        }
        if self._model:
            body["model"] = self._model
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        started = time.perf_counter()
        try:
            response = await self._client.post(
                f"{self.api_url}/images/generations", json=body, headers=headers
            )
        except httpx.TimeoutException as exc:
            raise ImageEngineError(
                f"le service d'images n'a pas répondu en {TIMEOUT_S / 60:.0f} min"
            ) from exc
        except httpx.HTTPError as exc:
            raise ImageEngineError(
                f"service d'images injoignable à {self.api_url} ({type(exc).__name__}) : est-il lancé, "
                "et l'adresse est-elle vue depuis Docker (host.docker.internal plutôt que 127.0.0.1) ?"
            ) from exc
        if response.status_code in (401, 403):
            raise ImageEngineError("service d'images : clé refusée (LUDIFUN_IMAGE_API_KEY)")
        if response.status_code == 404:
            raise ImageEngineError(
                "service d'images : pas de génération d'images à cette adresse (…/v1/images/generations) "
                "ou modèle inconnu (LUDIFUN_IMAGE_MODEL)"
            )
        if response.status_code == 429:
            raise ImageEngineError("service d'images : quota atteint, réessayer plus tard")
        if response.status_code >= 400:
            # Le corps n'est pas recopié : il peut reprendre le prompt (journaux sans contenu).
            raise ImageEngineError(f"service d'images : erreur {response.status_code}")
        try:
            items = response.json().get("data")
            first = items[0] if isinstance(items, list) and items else {}
        except (ValueError, AttributeError) as exc:
            raise ImageEngineError("service d'images : réponse illisible") from exc
        if not isinstance(first, dict):
            raise ImageEngineError("service d'images : réponse sans image")
        if first.get("b64_json"):
            data = decode_b64(first["b64_json"])
        elif isinstance(first.get("url"), str):
            data = await self._download(first["url"])
        else:
            raise ImageEngineError("service d'images : réponse sans image")
        return GeneratedImage(
            data, checked_image(data), self.name, self.model, round((time.perf_counter() - started) * 1000)
        )

    async def _download(self, url: str) -> bytes:
        if not url.startswith(("https://", "http://")):
            if url.startswith("data:"):
                return decode_b64(url)
            raise ImageEngineError("service d'images : adresse d'image invalide")
        try:
            async with self._client.stream("GET", url) as response:
                if response.status_code >= 400:
                    raise ImageEngineError(f"service d'images : image introuvable ({response.status_code})")
                data = b""
                async for chunk in response.aiter_bytes():
                    data += chunk
                    if len(data) > MAX_BYTES:
                        raise ImageEngineError("service d'images : image trop lourde")
                return data
        except httpx.HTTPError as exc:
            raise ImageEngineError(
                f"service d'images : téléchargement impossible ({type(exc).__name__})"
            ) from exc

    async def release(self) -> None:
        return None  # rien à libérer sur la carte graphique du PC
