"""« Voir ce qui se passe » : l'écran d'analyse montre l'IA étape par étape, et la raison d'un échec."""

import uuid

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.ports import AIError
from app.ai.providers.fake import FakeProvider
from app.db.models import Lesson
from app.services.lesson_diagnostics import explain
from app.services.live_calls import LIVE
from tests.api.helpers import family_with_device, upload_lesson


async def test_steps_of_a_successful_analysis(client: AsyncClient) -> None:
    family = await family_with_device(client)
    lesson = await upload_lesson(client, family["device"])
    diagnostics = lesson["diagnostics"]
    assert diagnostics["explanation"] is None
    stages = [s["stage"] for s in diagnostics["steps"]]
    assert stages[:2] == ["lecture de la leçon", "identification des notions"]
    assert "préparation des exercices" in stages
    assert {s["status"] for s in diagnostics["steps"]} == {"ok"}


async def test_the_reason_of_a_failure(client: AsyncClient, fake_llm: FakeProvider) -> None:
    fake_llm.overrides["ocr"] = AIError(
        "Ollama injoignable à http://host.docker.internal:11434 (ConnectError) : est-il lancé sur le PC ?"
    )
    family = await family_with_device(client)
    lesson = await upload_lesson(client, family["device"])
    assert lesson["status"] == "failed"
    diagnostics = lesson["diagnostics"]
    (step,) = diagnostics["steps"]
    assert step["stage"] == "lecture de la leçon" and step["status"] == "error"
    assert "ConnectError" in step["message"]
    assert "joindre Ollama" in diagnostics["explanation"]


async def test_live_steps_during_the_analysis(client: AsyncClient, db: AsyncSession) -> None:
    family = await family_with_device(client)
    lesson = await upload_lesson(client, family["device"])
    lesson_id = uuid.UUID(lesson["id"])
    await db.execute(update(Lesson).where(Lesson.id == lesson_id).values(status="analyzing"))
    await db.commit()
    LIVE.track(lesson_id, "ocr", "ollama/qwen2.5vl:7b")("ok", None)
    finish = LIVE.track(lesson_id, "analysis", "ollama/qwen2.5vl:7b")
    try:
        r = await client.get(
            f"/v1/lessons/{lesson['id']}", headers={"Authorization": f"Bearer {family['device']}"}
        )
    finally:
        finish("ok", None)
        LIVE.forget(lesson_id)
    steps = r.json()["diagnostics"]["steps"]
    assert [(s["stage"], s["status"]) for s in steps] == [
        ("lecture de la leçon", "ok"),
        ("identification des notions", "running"),
    ]


def test_explanations() -> None:
    assert "trop de temps" in explain("Ollama n'a pas répondu en 15 min (ReadTimeout) : modèle trop lourd")
    assert "clé d'API" in explain("API gemini 401 : API key not valid")
    assert "quota" in explain("API groq 429 : rate limit")
    assert "format attendu" in explain("réponse hors schéma : 3 validation errors")
    assert explain("inconnu") == "Erreur de l'IA."
