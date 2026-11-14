from app.ai.imagegen.cloudflare import DEFAULT_MODEL as CLOUDFLARE_MODEL
from app.ai.imagegen.cloudflare import DEFAULT_URL as CLOUDFLARE_URL
from app.ai.imagegen.cloudflare import CloudflareEngine
from app.ai.imagegen.comfyui import ComfyUiEngine
from app.ai.imagegen.fake import FakeImageEngine
from app.ai.imagegen.openai_images import OpenAiImagesEngine
from app.ai.imagegen.pollinations import DEFAULT_MODEL as POLLINATIONS_MODEL
from app.ai.imagegen.pollinations import DEFAULT_URL as POLLINATIONS_URL
from app.ai.imagegen.pollinations import PollinationsEngine
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
        case "pollinations" if settings.image_api_key and settings.image_api_key.get_secret_value():
            return PollinationsEngine(
                settings.image_api_key.get_secret_value(),
                settings.image_model or POLLINATIONS_MODEL,
                settings.image_url or POLLINATIONS_URL,
            )
        case "cloudflare" if (
            settings.image_api_key and settings.image_api_key.get_secret_value() and settings.image_account_id
        ):
            return CloudflareEngine(
                settings.image_api_key.get_secret_value(),
                settings.image_account_id,
                settings.image_model or CLOUDFLARE_MODEL,
                settings.image_url or CLOUDFLARE_URL,
            )
        case "openai" if settings.image_url:
            key = settings.image_api_key.get_secret_value() if settings.image_api_key else None
            return OpenAiImagesEngine(settings.image_url, key or None, settings.image_model or None)
        case "fake":
            return FakeImageEngine()
    return None
