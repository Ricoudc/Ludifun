import base64
import binascii

from app.ai.imagegen.ports import ImageEngineError
from app.ai.images import detect_media_type

TIMEOUT_S = 600.0  # une image SDXL sur une petite carte AMD : de quelques secondes à quelques minutes


def checked_image(data: bytes) -> str:
    """Type de l'image produite, vérifié par ses premiers octets (jamais par ce que dit le moteur)."""
    media_type = detect_media_type(data)
    if media_type not in ("image/png", "image/jpeg", "image/webp"):
        raise ImageEngineError("le moteur n'a pas renvoyé une image PNG, JPEG ou WebP")
    return media_type


def decode_b64(value: object) -> bytes:
    if not isinstance(value, str) or not value:
        raise ImageEngineError("réponse du moteur sans image")
    if value.startswith("data:"):
        value = value.split(",", 1)[-1]
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ImageEngineError("image illisible dans la réponse du moteur") from exc
