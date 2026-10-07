"""Moteurs d'images (étape 27) : stable-diffusion.cpp, ComfyUI, factice ; verrou de la carte."""

import asyncio
import base64
import io
import json
from typing import Any

import httpx
import pytest
from PIL import Image

from app.ai.imagegen.comfyui import ComfyUiEngine
from app.ai.imagegen.factory import image_engine_for
from app.ai.imagegen.fake import FakeImageEngine
from app.ai.imagegen.ports import ImageEngineError, ImageRequest
from app.ai.imagegen.sdcpp import SdCppEngine
from app.ai.providers.ollama import gpu_lock, unload_models
from app.config import Settings

REQUEST = ImageRequest("A dog in a meadow", "text", 1024, 1024, seed=42)


def png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (10, 200, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def client(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_sdcpp_txt2img() -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/sdapi/v1/txt2img"
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"images": [base64.b64encode(png()).decode()]})

    engine = SdCppEngine("http://pc:7860/", "sdxl_lightning_4step", client=client(handler))
    image = await engine.generate(REQUEST)
    assert image.media_type == "image/png" and image.engine == "sdcpp" and image.data == png()
    (body,) = sent
    assert body["steps"] == 4 and body["cfg_scale"] == 1.0
    assert (body["sampler_name"], body["scheduler"]) == ("euler", "sgm_uniform")
    assert (body["width"], body["height"], body["seed"]) == (1024, 1024, 42)


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(500, text="boom"), "erreur 500"),
        (httpx.Response(200, json={"images": []}), "sans image"),
        (httpx.Response(200, json={"images": [base64.b64encode(b"pas une image").decode()]}), "PNG"),
    ],
)
async def test_sdcpp_errors(response: httpx.Response, message: str) -> None:
    engine = SdCppEngine("http://pc:7860", "m", client=client(lambda request: response))
    with pytest.raises(ImageEngineError, match=message):
        await engine.generate(REQUEST)


async def test_sdcpp_not_started() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refusé", request=request)

    with pytest.raises(ImageEngineError, match="est-il lancé"):
        await SdCppEngine("http://pc:7860", "m", client=client(handler)).generate(REQUEST)


async def test_comfyui_prompt_history_view_free(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.ai.imagegen.comfyui.POLL_S", 0)
    calls: list[str] = []
    polls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.url.path == "/prompt":
            graph = json.loads(request.content)["prompt"]
            assert graph["4"]["inputs"]["ckpt_name"] == "sdxl_lightning_4step.safetensors"
            assert graph["3"]["inputs"]["steps"] == 4 and graph["3"]["inputs"]["scheduler"] == "sgm_uniform"
            return httpx.Response(200, json={"prompt_id": "p1"})
        if request.url.path == "/history/p1":
            polls["n"] += 1
            if polls["n"] == 1:
                return httpx.Response(200, json={})  # pas encore fini
            outputs = {"9": {"images": [{"filename": "ludifun_1.png", "subfolder": "", "type": "output"}]}}
            return httpx.Response(200, json={"p1": {"outputs": outputs, "status": {"status_str": "success"}}})
        if request.url.path == "/view":
            assert request.url.params["filename"] == "ludifun_1.png"
            return httpx.Response(200, content=png())
        if request.url.path == "/free":
            assert json.loads(request.content) == {"unload_models": True, "free_memory": True}
            return httpx.Response(200)
        return httpx.Response(404)

    engine = ComfyUiEngine("http://pc:8188", "sdxl_lightning_4step.safetensors", client=client(handler))
    image = await engine.generate(REQUEST)
    await engine.release()
    assert image.data == png() and image.engine == "comfyui"
    assert calls == ["POST /prompt", "GET /history/p1", "GET /history/p1", "GET /view", "POST /free"]


async def test_unload_ollama_before_drawing() -> None:
    unloaded: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": "qwen3-vl:8b", "model": "qwen3-vl:8b"}]})
        unloaded.append(json.loads(request.content))
        return httpx.Response(200, json={})

    assert await unload_models("http://pc:11434", client(handler)) == ["qwen3-vl:8b"]
    assert unloaded == [{"model": "qwen3-vl:8b", "keep_alive": 0}]

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("éteint", request=request)

    assert await unload_models("http://pc:11434", client(down)) == []  # Ollama éteint : rien à faire


async def test_one_graphics_card_per_machine() -> None:
    """Ollama et le moteur d'images sur le même PC (ports différents) : un seul verrou."""
    assert gpu_lock("http://192.168.1.76:11434") is gpu_lock("http://192.168.1.76:7860")
    assert gpu_lock("http://host.docker.internal:11434") is gpu_lock("http://localhost:7860")
    assert gpu_lock("http://192.168.1.76:11434") is not gpu_lock("http://192.168.1.80:11434")
    await asyncio.sleep(0)


def test_factory() -> None:
    assert image_engine_for(Settings(image_engine="none")) is None
    assert image_engine_for(Settings(image_engine="sdcpp")) is None  # sans adresse : pas d'images
    sd = image_engine_for(Settings(image_engine="sdcpp", image_url="http://pc:7860"))
    assert isinstance(sd, SdCppEngine) and sd.model == "sdxl_lightning_4step"
    comfy = image_engine_for(
        Settings(image_engine="comfyui", image_url="http://pc:8188", image_model="m.safetensors")
    )
    assert isinstance(comfy, ComfyUiEngine) and comfy.model == "m.safetensors"
    assert isinstance(image_engine_for(Settings(image_engine="fake")), FakeImageEngine)
