"""stable-diffusion.cpp (`sd-server`, moteur Vulkan) : un seul programme, sans Python ni kit AMD,
qui marche sur les Radeon RX 6600 sous Windows. Appelé par sa route compatible
« Automatic1111 » (`POST /sdapi/v1/txt2img`).

Lancé avec `--params-backend disk` (scripts Windows) : le modèle est relu sur le disque à chaque
image et la carte graphique est libérée ensuite, pour qu'Ollama retrouve sa place.
"""

import time

import httpx

from app.ai.imagegen.common import TIMEOUT_S, checked_image, decode_b64
from app.ai.imagegen.ports import GeneratedImage, ImageEngineError, ImageRequest


class SdCppEngine:
    name = "sdcpp"

    def __init__(self, base_url: str, model: str, client: httpx.AsyncClient | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = client or httpx.AsyncClient(timeout=TIMEOUT_S)

    async def generate(self, request: ImageRequest) -> GeneratedImage:
        body = {
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "width": request.width,
            "height": request.height,
            "steps": request.steps,
            "cfg_scale": request.cfg_scale,
            "sampler_name": request.sampler,
            "scheduler": request.scheduler,
            "seed": request.seed,
            "batch_size": 1,
        }
        started = time.perf_counter()
        try:
            response = await self._client.post(f"{self.base_url}/sdapi/v1/txt2img", json=body)
        except httpx.TimeoutException as exc:
            raise ImageEngineError(f"le moteur d'images n'a pas répondu en {TIMEOUT_S / 60:.0f} min") from exc
        except httpx.HTTPError as exc:
            raise ImageEngineError(
                f"moteur d'images injoignable à {self.base_url} ({type(exc).__name__}) : est-il lancé ?"
            ) from exc
        if response.status_code >= 400:
            raise ImageEngineError(f"moteur d'images : erreur {response.status_code} : {response.text[:200]}")
        try:
            images = response.json().get("images")
        except ValueError as exc:
            raise ImageEngineError("réponse du moteur d'images illisible") from exc
        data = decode_b64(images[0] if isinstance(images, list) and images else None)
        return GeneratedImage(
            data, checked_image(data), self.name, self.model, round((time.perf_counter() - started) * 1000)
        )

    async def release(self) -> None:
        return None  # --params-backend disk : rien ne reste sur la carte entre deux images
