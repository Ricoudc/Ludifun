"""Leçon envoyée en fichier : PDF, Word (.docx) ou LibreOffice (.odt).

Le texte est extrait ici, sans IA ; il suit ensuite le chemin d'une leçon collée. Un PDF scanné
(pages en images, sans texte) donne ses images, qui suivent le chemin des photos. Le fichier n'est
jamais enregistré : il est lu en mémoire puis oublié, comme les photos (§15).

Garde-fous : taille du fichier limitée par la route, nombre de pages lues limité, archive Word
ou LibreOffice dont le texte décompressé est trop gros refusée (bombe de décompression), XML
avec déclaration de type refusé (entités).
"""

import io
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.ai.images import detect_media_type
from app.ai.ports import PageImage

MAX_PDF_PAGES = 20  # pages lues pour le texte
MAX_XML_BYTES = 5 * 1024 * 1024  # texte décompressé d'un .docx ou d'un .odt

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"


class DocumentError(ValueError):
    """Fichier refusé : `code` pour l'application, `message` pour la famille."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


@dataclass(frozen=True)
class Document:
    kind: str  # "pdf", "docx", "odt"
    text: str = ""
    images: list[PageImage] = field(default_factory=list)  # PDF scanné : une image par page


def kind_of(data: bytes) -> str | None:
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"\xd0\xcf\x11\xe0"):
        return "doc"  # ancien Word (avant 2007)
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile:
            return None
        if "word/document.xml" in names:
            return "docx"
        if "content.xml" in names and "mimetype" in names:
            return "odt"
    return None


def read_document(data: bytes, max_pages: int, max_image_bytes: int) -> Document:
    """Le texte du document, ou les images de ses pages s'il n'a pas de texte."""
    match kind_of(data):
        case "pdf":
            return _pdf(data, max_pages, max_image_bytes)
        case "docx":
            return Document("docx", text=_paragraphs(_xml(data, "word/document.xml"), "docx"))
        case "odt":
            return Document("odt", text=_paragraphs(_xml(data, "content.xml"), "odt"))
        case "doc":
            raise DocumentError(
                "old_word_format",
                "Ce fichier Word est d'un ancien format : enregistre-le en .docx ou en PDF.",
            )
    raise DocumentError(
        "unsupported_document", "Envoie un PDF, un fichier Word (.docx) ou LibreOffice (.odt)."
    )


def _pdf(data: bytes, max_pages: int, max_image_bytes: int) -> Document:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise DocumentError("protected_document", "Ce PDF est protégé par un mot de passe.")
        pages = reader.pages[:MAX_PDF_PAGES]
        text = "\n\n".join(t.strip() for page in pages if (t := page.extract_text() or "").strip())
        if text:
            return Document("pdf", text=text)
        # PDF scanné : la plus grande image de chaque page, lue ensuite comme une photo.
        images = []
        for page in reader.pages[:max_pages]:
            found = [img.data for img in page.images if len(img.data) <= max_image_bytes]
            best = max(found, key=len, default=None)
            media_type = detect_media_type(best) if best else None
            if best and media_type:
                images.append(PageImage(best, media_type))
    except DocumentError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError, NotImplementedError) as exc:
        raise DocumentError("unreadable_document", "Ce PDF n'a pas pu être lu.") from exc
    if not images:
        raise DocumentError("unreadable_document", "Ce PDF ne contient ni texte ni page lisible.")
    return Document("pdf", images=images)


def _xml(data: bytes, name: str) -> ET.Element:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if archive.getinfo(name).file_size > MAX_XML_BYTES:
                raise DocumentError("too_long", "Ce document est trop long pour une leçon.")
            with archive.open(name) as part:
                raw = part.read(MAX_XML_BYTES + 1)
    except (zipfile.BadZipFile, KeyError, OSError, RuntimeError) as exc:
        raise DocumentError("unreadable_document", "Ce document n'a pas pu être lu.") from exc
    if len(raw) > MAX_XML_BYTES:
        raise DocumentError("too_long", "Ce document est trop long pour une leçon.")
    if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
        raise DocumentError("unreadable_document", "Ce document n'a pas pu être lu.")
    try:
        return ET.fromstring(raw)
    except ET.ParseError as exc:
        raise DocumentError("unreadable_document", "Ce document n'a pas pu être lu.") from exc


def _paragraphs(root: ET.Element, kind: str) -> str:
    """Un paragraphe (ou un titre, une case de tableau) par ligne, dans l'ordre du document."""
    lines = []
    if kind == "docx":
        for paragraph in root.iter(f"{_W}p"):
            parts = []
            for node in paragraph.iter():
                if node.tag == f"{_W}t":
                    parts.append(node.text or "")
                elif node.tag == f"{_W}tab":
                    parts.append("\t")
                elif node.tag in (f"{_W}br", f"{_W}cr"):
                    parts.append("\n")
            lines.append("".join(parts).strip())
    else:
        for node in root.iter():
            if node.tag in (f"{_TEXT}p", f"{_TEXT}h"):
                lines.append(_odt_text(node).strip())
    return "\n".join(line for line in lines if line)


def _odt_text(node: ET.Element) -> str:
    """Le texte d'un paragraphe LibreOffice : espaces répétés, tabulations, retours à la ligne."""
    parts = [node.text or ""]
    for child in node:
        if child.tag == f"{_TEXT}s":
            parts.append(" " * int(child.get(f"{_TEXT}c", "1")))
        elif child.tag == f"{_TEXT}tab":
            parts.append("\t")
        elif child.tag == f"{_TEXT}line-break":
            parts.append("\n")
        elif child.tag not in (f"{_TEXT}p", f"{_TEXT}h"):  # un paragraphe imbriqué est lu seul
            parts.append(_odt_text(child))
        parts.append(child.tail or "")
    return "".join(parts)
