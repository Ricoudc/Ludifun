from app.ai.imagegen.comfyui import ComfyUiEngine
from app.ai.imagegen.fake import FakeImageEngine
from app.ai.imagegen.ports import ImageEngine
from app.ai.imagegen.sdcpp import SdCppEngine
from app.config import Settings

DEFAULT_MODEL = "sdxl_lightning_4step"


def image_engine_for(settings: Settings) -> ImageEngine | None:
    """Le moteur choisi par `LUDIFUN_IMAGE_ENGINE` ; None : pas d'images (réglage par défaut)."""
    match settings.image_engine:
        case "sdcpp" if settings.image_url:
            return SdCppEngine(settings.image_url, settings.image_model or DEFAULT_MODEL)
        case "comfyui" if settings.image_url:
            return ComfyUiEngine(settings.image_url, settings.image_model or f"{DEFAULT_MODEL}.safetensors")
        case "fake":
            return FakeImageEngine()
    return None
