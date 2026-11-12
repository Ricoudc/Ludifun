"""Assistant parent (§46) : réponses calculées à partir des données réelles de l'enfant."""

from datetime import timedelta
from zoneinfo import ZoneInfo

from httpx import AsyncClient

from app import clock
from tests.api.helpers import auth, family_with_device, upload_lesson


async def test_the_parent_asks_and_gets_answers_from_real_data(client: AsyncClient) -> None:
    family = await family_with_device(client)
    parent, child_id = family["parent"], family["child"]["id"]
    url = f"/v1/children/{child_id}/assistant"
    lesson = await upload_lesson(client, family["device"])

    answers = (await client.get(url, headers=auth(parent))).json()["answers"]
    assert [a["question"] for a in answers] == ["week", "help", "progress"]
    week = answers[0]
    assert week["title"] == "Sur quoi faire travailler Emma cette semaine ?"
    # Rien de travaillé : on part des notions les plus importantes de la leçon.
    assert week["lines"][0].startswith("Pas encore assez de séances")
    assert any("« 1789 »" in line for line in week["lines"])
    assert "0 notion travaillée sur 8" in week["based_on"]

    # Un contrôle à venir ajoute sa question.
    today = clock.now().astimezone(ZoneInfo("Europe/Paris")).date()
    r = await client.post(
        f"/v1/children/{child_id}/exams",
        json={
            "title": "Contrôle d'histoire",
            "exam_date": (today + timedelta(days=4)).isoformat(),
            "lesson_ids": [lesson["id"]],
        },
        headers=auth(parent),
    )
    assert r.status_code == 201, r.text
    answers = (await client.get(url, headers=auth(parent))).json()["answers"]
    exam = next(a for a in answers if a["question"] == "exam")
    assert exam["title"] == "Le contrôle « Contrôle d'histoire » : où en est Emma ?"
    assert "✅ Notions acquises : 0 sur 8." in exam["lines"]
