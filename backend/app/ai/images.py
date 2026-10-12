"""Photos : reconnaissance du format à partir des premiers octets (jamais du nom), réduction."""

import io

from PIL import Image

from app.ai.ports import MediaType

HEIC_BRANDS = (b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1")


def detect_media_type(data: bytes) -> MediaType | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return None


def is_heic(data: bytes) -> bool:
    """Photo HEIC d'iPhone : à convertir en JPEG sur le téléphone avant l'envoi."""
    return data[4:8] == b"ftyp" and data[8:12] in HEIC_BRANDS


def shrink(data: bytes, max_side: int) -> bytes:
    """Photo réduite (JPEG) si son grand côté dépasse `max_side` ; sinon, ou illisible, telle quelle.

    Une IA installée sur le PC lit une photo bien plus vite quand elle est plus petite : le
    nombre de morceaux d'image à traiter suit la surface.
    """
    try:
        with Image.open(io.BytesIO(data)) as image:
            if max(image.size) <= max_side:
                return data
            image.thumbnail((max_side, max_side))
            out = io.BytesIO()
            image.convert("RGB").save(out, format="JPEG", quality=88)
            return out.getvalue()
    except (OSError, ValueError):
        return data
