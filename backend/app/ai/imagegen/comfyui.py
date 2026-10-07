"""ComfyUI, par son API locale : le moteur reste invisible (personne n'ouvre son interface).

Un graphe « texte → image » SDXL est envoyé (`POST /prompt`), Ludifun attend le résultat
(`GET /history/{id}`), récupère l'image (`GET /view`), puis vide la carte graphique
(`POST /free`) pour qu'Ollama retrouve sa place.
"""

import asyncio
import contextlib
import time
import uuid
from typing import Any

import httpx

from app.ai.imagegen.common import TIMEOUT_S, checked_image
from app.ai.imagegen.ports import GeneratedImage, ImageEngineError, ImageRequest

POLL_S = 1.0


def workflow(request: ImageRequest, checkpoint: str) -> dict[str, Any]:
    """Graphe ComfyUI (format API) : modèle, deux textes, image vide, échantillonneur, décodage."""
    return {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": request.width, "height": request.height, "batch_size": 1},
        },
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": request.prompt, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": request.negative_prompt, "clip": ["4", 1]}},
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": request.seed,
                "steps": request.steps,
                "cfg": request.cfg_scale,
                "sampler_name": request.sampler,
                "scheduler": request.scheduler,
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "ludifun", "images": ["8", 0]}},
    }


class ComfyUiEngine:
    name = "comfyui"

    def __init__(self, base_url: str, model: str, client: httpx.AsyncClient | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model  # nom du fichier dans models/checkpoints
        self._client = client or httpx.AsyncClient(timeout=60)

    async def generate(self, request: ImageRequest) -> GeneratedImage:
        started = time.perf_counter()
        try:
            sent = await self._client.post(
                f"{self.base_url}/prompt",
                json={"prompt": workflow(request, self.model), "client_id": str(uuid.uuid4())},
            )
            if sent.status_code >= 400:
                raise ImageEngineError(f"ComfyUI : erreur {sent.status_code} : {sent.text[:200]}")
            prompt_id = sent.json()["prompt_id"]
            output = await self._wait(prompt_id, started)
            image = output["images"][0]
            view = await self._client.get(
                f"{self.base_url}/view",
                params={
                    "filename": image["filename"],
                    "subfolder": image.get("subfolder", ""),
                    "type": "output",
                },
            )
        except httpx.HTTPError as exc:
            raise ImageEngineError(
                f"ComfyUI injoignable à {self.base_url} ({type(exc).__name__}) : est-il lancé ?"
            ) from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ImageEngineError("réponse de ComfyUI inattendue") from exc
        if view.status_code >= 400:
            raise ImageEngineError(f"ComfyUI : image introuvable ({view.status_code})")
        data = view.content
        return GeneratedImage(
            data, checked_image(data), self.name, self.model, round((time.perf_counter() - started) * 1000)
        )

    async def _wait(self, prompt_id: str, started: float) -> dict[str, Any]:
        while time.perf_counter() - started < TIMEOUT_S:
            history = (await self._client.get(f"{self.base_url}/history/{prompt_id}")).json()
            entry = history.get(prompt_id)
            if entry:
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    raise ImageEngineError("ComfyUI a échoué pendant le calcul")
                outputs: dict[str, Any] = entry.get("outputs", {})
                found: dict[str, Any] | None = next((o for o in outputs.values() if o.get("images")), None)
                if found is not None:
                    return found
            await asyncio.sleep(POLL_S)
        raise ImageEngineError(f"ComfyUI n'a pas fini en {TIMEOUT_S / 60:.0f} min")

    async def release(self) -> None:
        # Un échec n'empêche rien : la prochaine image rechargera de toute façon.
        with contextlib.suppress(httpx.HTTPError):
            await self._client.post(
                f"{self.base_url}/free", json={"unload_models": True, "free_memory": True}
            )
