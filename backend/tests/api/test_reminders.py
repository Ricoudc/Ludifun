"""Rappels du jour (§48), côté parent : calculés à partir des données réelles de chaque enfant."""

from datetime import timedelta
from zoneinfo import ZoneInfo

from httpx import AsyncClient

from app import clock
from tests.api.helpers import auth, family_with_device, upload_lesson


async def test_an_exam_tomorrow_then_nothing_once_revised(client: AsyncClient) -> None:
    family = await family_with_device(client)
    parent, token, child_id = family["parent"], family["device"], family["child"]["id"]
    lesson = await upload_lesson(client, token)
    # Pas de contrôle, pas d'habitude, rien à revoir : pas de rappel.
    assert (await client.get("/v1/parent/reminders", headers=auth(parent))).json() == []

    tomorrow = clock.now().astimezone(ZoneInfo("Europe/Paris")).date() + timedelta(days=1)
    await client.post(
        f"/v1/children/{child_id}/exams",
        json={"title": "Révolution", "exam_date": tomorrow.isoformat(), "lesson_ids": [lesson["id"]]},
        headers=auth(parent),
    )
    found = (await client.get("/v1/parent/reminders", headers=auth(parent))).json()
    assert len(found) == 1 and found[0]["child_id"] == child_id and found[0]["kind"] == "exam"
    assert found[0]["text"].startswith("📅 Contrôle « Révolution » demain")

    # L'enfant révise : plus de rappel aujourd'hui.
    session = (await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))).json()
    item = session["items"][0]
    await client.post(
        f"/v1/sessions/{session['id']}/attempts",
        json={"item_id": item["id"], "response": {"skipped": True}},
        headers=auth(token),
    )
    assert (await client.get("/v1/parent/reminders", headers=auth(parent))).json() == []
    # L'appareil de l'enfant n'y a pas accès.
    assert (await client.get("/v1/parent/reminders", headers=auth(token))).status_code == 403
