"""Leçon envoyée en PDF, Word ou LibreOffice : son texte est analysé comme une leçon collée, un
PDF scanné comme des photos ; le fichier n'est jamais enregistré."""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.fake import DEMO_LESSON, FakeProvider, LessonScript
from app.db.models import Lesson, LessonPage
from tests.api.helpers import auth, family_with_device
from tests.support_documents import docx, odt, scanned_pdf

HISTORY = LessonScript.from_file(DEMO_LESSON).ocr_text
URL = "/v1/lessons/document"


async def send(client: AsyncClient, token: str, name: str, data: bytes, mime: str) -> dict[str, object]:
    r = await client.post(URL, files={"document": (name, data, mime)}, headers=auth(token))
    assert r.status_code == 202, r.text
    lesson: dict[str, object] = (
        await client.get(f"/v1/lessons/{r.json()['id']}", headers=auth(token))
    ).json()
    return lesson


async def test_a_word_lesson_is_analysed_like_a_pasted_one(
    client: AsyncClient, db: AsyncSession, fake_llm: FakeProvider
) -> None:
    token = (await family_with_device(client))["device"]
    word = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    lesson = await send(client, token, "revolution.docx", docx(HISTORY.split("\n")), word)
    assert lesson["status"] == "ready" and lesson["source"] == "text"
    assert lesson["title"] == "La Révolution française"
    assert fake_llm.calls[0][0] == "analysis"  # pas de lecture de photo
    assert (await db.scalar(select(LessonPage.ocr_text))) == HISTORY  # le texte, pas le fichier

    libre = await send(client, token, "revolution.odt", odt(HISTORY.split("\n")), "application/octet-stream")
    assert libre["status"] == "ready" and libre["source"] == "text"


async def test_a_scanned_pdf_is_read_like_photos(client: AsyncClient, db: AsyncSession) -> None:
    token = (await family_with_device(client))["device"]
    lesson = await send(client, token, "scan.pdf", scanned_pdf(pages=2), "application/pdf")
    assert lesson["status"] == "ready" and lesson["source"] == "photo"
    row = await db.get(Lesson, lesson["id"])
    assert row is not None and row.page_count == 2


async def test_refused_documents(client: AsyncClient) -> None:
    token = (await family_with_device(client))["device"]

    async def code(data: bytes, name: str = "lecon.doc") -> tuple[int, str]:
        r = await client.post(
            URL, files={"document": (name, data, "application/msword")}, headers=auth(token)
        )
        return r.status_code, r.json()["error"]["code"]

    assert await code(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 100) == (415, "old_word_format")
    assert await code(b"bonjour", "lecon.txt") == (415, "unsupported_document")
    assert await code(b"%PDF-1.4 abime", "lecon.pdf") == (422, "unreadable_document")
    assert await code(docx(["Trop court."]), "lecon.docx") == (422, "text_too_short")
    assert await code(docx(["mot " * 6000]), "lecon.docx") == (422, "too_long")
    assert await code(b"%PDF-" + b"0" * (15 * 1024 * 1024), "gros.pdf") == (413, "document_too_large")


async def test_a_parent_token_cannot_send_without_choosing_a_child(client: AsyncClient) -> None:
    parent = (await family_with_device(client))["parent"]
    r = await client.post(URL, files={"document": ("l.docx", docx([HISTORY]), "x")}, headers=auth(parent))
    assert r.status_code in (403, 422), r.text
