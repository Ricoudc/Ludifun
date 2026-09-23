"""Reconnaissance du format d'une photo à partir de ses premiers octets (jamais de son nom)."""

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
