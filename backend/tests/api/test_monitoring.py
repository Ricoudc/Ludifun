"""Page /suivi et rapport texte : les appels à l'IA, sans donnée personnelle."""

import uuid

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Lesson
from app.services.live_calls import LIVE
from app.services.monitoring import clean_message
from tests.api.helpers import family_with_device, upload_lesson


async def test_page_and_live_calls(client: AsyncClient, db: AsyncSession) -> None:
    family = await family_with_device(client)
    lesson = await upload_lesson(client, family["device"])
    assert lesson["status"] == "ready"

    page = await client.get("/suivi")
    assert page.status_code == 200 and "Suivi de l'IA" in page.text
    assert "script-src 'self'" in page.headers["content-security-policy"]
    assert (await client.get("/suivi/suivi.js")).headers["content-type"].startswith("text/javascript")

    data = (await client.get("/suivi/donnees")).json()
    assert data["running"] == [] and data["server_ai"].startswith("fake")
    (recent,) = data["recent"]
    assert recent["lesson"] == lesson["id"][:8] and recent["state"] == "ready" and recent["status"] == "prête"
    assert [s["status"] for s in recent["steps"]] and all(s["status"] == "ok" for s in recent["steps"])
    assert data["stats"] and data["errors"] == []

    # Une analyse en cours : l'appel à l'IA et sa durée apparaissent.
    lesson_id = uuid.UUID(lesson["id"])
    await db.execute(update(Lesson).where(Lesson.id == lesson_id).values(status="reading"))
    await db.commit()
    finish = LIVE.track(lesson_id, "ocr", "ollama/qwen2.5vl:7b")
    try:
        running = (await client.get("/suivi/donnees")).json()["running"]
    finally:
        finish("ok", None)
        LIVE.forget(lesson_id)
    assert running[0]["lesson"] == lesson["id"][:8]
    assert running[0]["calls"][0] | {"elapsed_s": 0} == {
        "stage": "lecture de la leçon",
        "model": "ollama/qwen2.5vl:7b",
        "elapsed_s": 0,
    }

    text = (await client.get("/suivi/rapport.txt")).text
    assert "== Analyses en cours ==" in text and lesson["id"][:8] in text
    assert "Révolution" not in text and "Révolution" not in str(data)  # ni titre ni texte de leçon
    assert "@" not in text  # ni e-mail


async def test_monitoring_can_be_closed(app: FastAPI, client: AsyncClient) -> None:
    app.state.settings = app.state.settings.model_copy(update={"monitoring": False})
    for path in ("/suivi", "/suivi/donnees", "/suivi/rapport.txt"):
        assert (await client.get(path)).status_code == 404


def test_error_messages_drop_lesson_content() -> None:
    message = (
        "réponse hors schéma : 1 validation error [type=missing, "
        "input_value={'texte': 'Louis XVI'}, input_type=dict]"
    )
    assert "Louis" not in clean_message(message) and "input_value=…" in clean_message(message)
    assert len(clean_message("x" * 500)) == 200
