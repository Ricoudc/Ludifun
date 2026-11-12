"""Petits documents fabriqués pour les tests : Word (.docx), LibreOffice (.odt), PDF avec texte et
PDF scanné (une image par page)."""

import io
import zipfile
from xml.sax.saxutils import escape

from PIL import Image

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
TEXT = 'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"'
OFFICE = 'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"'


def docx(paragraphs: list[str], body_extra: str = "") -> bytes:
    """Un paragraphe par élément ; une tabulation « \\t » devient une tabulation Word."""
    runs = []
    for paragraph in paragraphs:
        parts = paragraph.split("\t")
        inner = "<w:tab/>".join(f'<w:t xml:space="preserve">{escape(p)}</w:t>' for p in parts)
        runs.append(f"<w:p><w:r>{inner}</w:r></w:p>")
    body = "".join(runs) + body_extra
    xml = f'<?xml version="1.0" encoding="UTF-8"?><w:document {W}><w:body>{body}</w:body></w:document>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", xml)
    return buffer.getvalue()


def odt(paragraphs: list[str], title: str | None = None) -> bytes:
    heading = f"<text:h>{escape(title)}</text:h>" if title else ""
    body = "".join(f"<text:p>{escape(p)}</text:p>" for p in paragraphs)
    xml = (
        f'<?xml version="1.0" encoding="UTF-8"?><office:document-content {OFFICE} {TEXT}>'
        f"<office:body><office:text>{heading}{body}</office:text></office:body></office:document-content>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        archive.writestr("content.xml", xml)
    return buffer.getvalue()


def text_pdf(lines: list[str]) -> bytes:
    """Un PDF d'une page, police Helvetica, une ligne de texte par élément."""

    def literal(line: str) -> bytes:
        raw = line.encode("cp1252")
        return b"(" + raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"

    content = b"BT /F1 12 Tf 14 TL 40 800 Td " + b" ".join(literal(line) + b" '" for line in lines) + b" ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def scanned_pdf(pages: int = 2) -> bytes:
    """Un PDF sans texte : une photo (JPEG) par page, comme un scanner."""
    images = [Image.new("RGB", (120, 170), (255, 255 - 40 * i, 255)) for i in range(pages)]
    buffer = io.BytesIO()
    images[0].save(buffer, "PDF", save_all=True, append_images=images[1:])
    return buffer.getvalue()
