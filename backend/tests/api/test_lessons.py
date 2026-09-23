import copy
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.ports import AIError
from app.ai.providers.fake import FakeProvider, analysis_output
from app.db.models import AiRun, KnowledgeMaterial, Lesson, LessonPage
from app.services.lesson_processing import recover_interrupted_lessons
from tests.api.helpers import PHOTO, auth, family_with_device, upload_lesson


async def test_upload_and_analysis(client: AsyncClient, db: AsyncSession) -> None:
    family = await family_with_device(client)
    files = [("pages", ("p1.jpg", PHOTO, "image/jpeg")), ("pages", ("p2.jpg", PHOTO, "image/jpeg"))]
    accepted = await client.post("/v1/lessons", files=files, headers=auth(family["device"]))
    assert accepted.status_code == 202 and accepted.json()["status"] == "uploaded"

    lesson = (await client.get(f"/v1/lessons/{accepted.json()['id']}", headers=auth(family["device"]))).json()
    assert lesson["status"] == "ready"
    assert lesson["steps"] == {"reading": "done", "analyzing": "done", "generating": "done"}
    assert (lesson["subject"], lesson["grade"], lesson["title"]) == (
        "history",
        "CM1",
        "La Révolution française",
    )
    assert lesson["objective"].startswith("Connaître")
    importances = [k["importance"] for k in lesson["knowledge"]]
    assert len(importances) == 8 and importances == sorted(importances, reverse=True)
    assert lesson["next_review_at"] is None and not lesson["mastered"]

    # Seul le texte lu est gardé ; les appels IA sont journalisés.
    assert await db.scalar(select(func.count()).select_from(LessonPage)) == 1
    assert await db.scalar(select(func.count()).select_from(KnowledgeMaterial)) == 8
    stages = (await db.scalars(select(AiRun.stage).order_by(AiRun.created_at))).all()
    assert sorted(stages) == ["analysis", "material", "material", "ocr"]

    listed = (await client.get("/v1/lessons", headers=auth(family["device"]))).json()
    assert [(item["id"], item["status"]) for item in listed] == [(lesson["id"], "ready")]


async def test_upload_validation(client: AsyncClient) -> None:
    token = (await family_with_device(client))["device"]

    async def post(files: list[Any]) -> Any:
        return await client.post("/v1/lessons", files=files, headers=auth(token))

    jpeg = ("pages", ("p.jpg", PHOTO, "image/jpeg"))
    assert (await post([])).status_code == 422
    assert (await post([jpeg] * 7)).json()["error"]["code"] == "invalid_page_count"
    too_big = ("pages", ("p.jpg", PHOTO + b"0" * (8 * 1024 * 1024), "image/jpeg"))
    assert (await post([too_big])).status_code == 413
    pdf = ("pages", ("p.pdf", b"%PDF-1.7 ...", "application/pdf"))
    assert (await post([pdf])).json()["error"]["code"] == "unsupported_media_type"
    heic = ("pages", ("p.heic", b"\x00\x00\x00\x18ftypheic" + b"0" * 20, "image/heic"))
    r = await post([heic])
    assert r.status_code == 415 and r.json()["error"]["code"] == "heic_not_supported"


async def test_not_a_lesson(client: AsyncClient, fake_llm: FakeProvider) -> None:
    fake_llm.overrides["analysis"] = analysis_output(
        {"is_lesson": False, "lesson": None, "knowledge": [], "warnings": []}
    )
    token = (await family_with_device(client))["device"]
    lesson = await upload_lesson(client, token)
    assert (lesson["status"], lesson["failure_reason"]) == ("failed", "not_a_lesson")
    assert lesson["steps"] is None and lesson["failure_message"] == "Ça ne ressemble pas à une leçon."
    assert not lesson["can_retry"]
    r = await client.post(f"/v1/lessons/{lesson['id']}/retry", headers=auth(token))
    assert r.status_code == 409


async def test_retry_after_an_ai_error(client: AsyncClient, fake_llm: FakeProvider, db: AsyncSession) -> None:
    good = analysis_output(copy.deepcopy(fake_llm.script.analysis))
    fake_llm.overrides["analysis"] = lambda attempt, _: AIError("API 529") if attempt == 1 else good
    token = (await family_with_device(client))["device"]
    lesson = await upload_lesson(client, token)
    assert (lesson["status"], lesson["failure_reason"], lesson["can_retry"]) == ("failed", "ai_error", True)

    assert (await client.post(f"/v1/lessons/{lesson['id']}/retry", headers=auth(token))).status_code == 202
    retried = (await client.get(f"/v1/lessons/{lesson['id']}", headers=auth(token))).json()
    assert retried["status"] == "ready" and len(retried["knowledge"]) == 8
    # La relance repart du texte déjà lu : pas de nouvel appel OCR.
    assert [stage for stage, _ in fake_llm.calls].count("ocr") == 1
    assert await db.scalar(select(func.count()).select_from(AiRun).where(AiRun.status == "error")) == 1


async def test_grade_correction_and_deletion(client: AsyncClient) -> None:
    token = (await family_with_device(client))["device"]
    lesson = await upload_lesson(client, token)
    patched = await client.patch(f"/v1/lessons/{lesson['id']}", json={"grade": "CM2"}, headers=auth(token))
    assert patched.json()["grade"] == "CM2"
    assert (
        await client.patch(f"/v1/lessons/{lesson['id']}", json={"grade": "L3"}, headers=auth(token))
    ).status_code == 422
    assert (await client.delete(f"/v1/lessons/{lesson['id']}", headers=auth(token))).status_code == 204
    assert (await client.get(f"/v1/lessons/{lesson['id']}", headers=auth(token))).status_code == 404


async def test_parent_photographs_a_lesson_for_the_child(client: AsyncClient) -> None:
    family = await family_with_device(client)
    lesson = await upload_lesson(client, family["parent"], child_id=family["child"]["id"])
    assert lesson["status"] == "ready"
    seen_by_child = (await client.get("/v1/lessons", headers=auth(family["device"]))).json()
    assert [item["id"] for item in seen_by_child] == [lesson["id"]]


async def test_daily_lesson_limit(client: AsyncClient, app: FastAPI) -> None:
    family = await family_with_device(client)
    for _ in range(20):
        app.state.rate_limiter.hit(f"lessons:{family['child']['id']}", 20, 86400)
    files = [("pages", ("p.jpg", PHOTO, "image/jpeg"))]
    r = await client.post("/v1/lessons", files=files, headers=auth(family["device"]))
    assert r.status_code == 429


async def test_lessons_of_another_family_are_invisible(client: AsyncClient) -> None:
    emma = await family_with_device(client, "a@example.fr")
    leo = await family_with_device(client, "b@example.fr")
    lesson = await upload_lesson(client, emma["device"])
    for method, path in (
        ("GET", ""),
        ("PATCH", ""),
        ("DELETE", ""),
        ("POST", "/retry"),
        ("POST", "/sessions"),
    ):
        body = {"grade": "CM2"} if method == "PATCH" else {} if path == "/sessions" else None
        r = await client.request(
            method, f"/v1/lessons/{lesson['id']}{path}", json=body, headers=auth(leo["device"])
        )
        assert r.status_code == 404, (method, path)
    assert (await client.get("/v1/lessons", headers=auth(leo["device"]))).json() == []


async def test_interrupted_analyses_are_recovered_at_startup(
    client: AsyncClient, db: AsyncSession, app: FastAPI
) -> None:
    token = (await family_with_device(client))["device"]
    stuck = await upload_lesson(client, token)
    recent = await upload_lesson(client, token)
    await db.execute(
        update(Lesson)
        .where(Lesson.id == stuck["id"])
        .values(status="analyzing", updated_at=datetime.now(UTC) - timedelta(minutes=30))
    )
    await db.execute(update(Lesson).where(Lesson.id == recent["id"]).values(status="reading"))
    await db.commit()

    assert await recover_interrupted_lessons(app.state.database) == 1
    after = (await client.get(f"/v1/lessons/{stuck['id']}", headers=auth(token))).json()
    assert (after["status"], after["failure_reason"], after["can_retry"]) == ("failed", "ai_error", True)
    still_running = (await client.get(f"/v1/lessons/{recent['id']}", headers=auth(token))).json()
    assert still_running["status"] == "reading"  # moins de 10 minutes : on la laisse finir
