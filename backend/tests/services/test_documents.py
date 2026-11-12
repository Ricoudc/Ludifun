"""Leçon en fichier : le texte d'un PDF, d'un Word ou d'un LibreOffice est lu sans IA ; un PDF
scanné donne ses images ; un fichier abîmé, protégé, trop gros ou d'un autre format est refusé
avec un message pour la famille."""

import io
import zipfile

import pytest
from pypdf import PdfWriter

from app.services.documents import MAX_XML_BYTES, DocumentError, kind_of, read_document
from tests.support_documents import docx, odt, scanned_pdf, text_pdf

LIMITS = {"max_pages": 6, "max_image_bytes": 8 * 1024 * 1024}


def test_word_paragraphs_tabs_and_accents() -> None:
    data = docx(["Les fractions", "Le numérateur\test au-dessus.", "", "3/4 : trois quarts"])
    read = read_document(data, **LIMITS)
    assert read.kind == "docx" and not read.images
    assert read.text == "Les fractions\nLe numérateur\test au-dessus.\n3/4 : trois quarts"


def test_word_tables_are_read_in_order() -> None:
    table = (
        "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>7 × 8</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>56</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
    )
    read = read_document(docx(["La table de 7"], body_extra=table), **LIMITS)
    assert read.text == "La table de 7\n7 × 8\n56"


def test_libreoffice_headings_and_paragraphs() -> None:
    read = read_document(
        odt(["Le verbe change selon la personne.", "Je chante."], title="Le présent"), **LIMITS
    )
    assert read.kind == "odt"
    assert read.text == "Le présent\nLe verbe change selon la personne.\nJe chante."


def test_pdf_with_text() -> None:
    read = read_document(text_pdf(["La Révolution française", "Le 14 juillet 1789"]), **LIMITS)
    assert read.kind == "pdf" and not read.images
    assert "Révolution française" in read.text and "14 juillet 1789" in read.text


def test_scanned_pdf_gives_one_image_per_page() -> None:
    read = read_document(scanned_pdf(pages=3), **LIMITS)
    assert read.text == "" and len(read.images) == 3
    assert all(i.media_type == "image/jpeg" and i.data.startswith(b"\xff\xd8") for i in read.images)
    assert len(read_document(scanned_pdf(pages=3), max_pages=2, max_image_bytes=10**7).images) == 2


def protected_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("secret")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def zipped(name: str, content: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, content)
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 100, "old_word_format"),
        (b"\x89PNG\r\n\x1a\n" + b"\0" * 50, "unsupported_document"),
        (zipped("autre.txt", b"rien"), "unsupported_document"),
        (b"%PDF-1.4\n pas vraiment un PDF", "unreadable_document"),
        (protected_pdf(), "protected_document"),
        (blank_pdf(), "unreadable_document"),
        (zipped("word/document.xml", b"<w:document><w:body>"), "unreadable_document"),
        (
            zipped("word/document.xml", b'<!DOCTYPE d [<!ENTITY a "aaaa">]><d>&a;</d>'),
            "unreadable_document",
        ),
        (zipped("word/document.xml", b" " * (MAX_XML_BYTES + 1)), "too_long"),  # bombe compressée
    ],
)
def test_refused_files(data: bytes, code: str) -> None:
    with pytest.raises(DocumentError) as refused:
        read_document(data, **LIMITS)
    assert refused.value.code == code and refused.value.message


def test_kind_of() -> None:
    assert kind_of(docx(["x"])) == "docx" and kind_of(odt(["x"])) == "odt"
    assert kind_of(text_pdf(["x"])) == "pdf" and kind_of(b"PK\x03\x04abime") is None
