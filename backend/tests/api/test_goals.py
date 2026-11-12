"""Critère de fin de l'étape 16 : un contrôle saisi par le parent donne un plan suivi par l'enfant
(mission du jour) et recalculé après chaque séance ; le temps quotidien règle la durée des
séances ; la matière prioritaire passe en premier."""

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.fake import REFERENCE_LESSONS, FakeProvider, LessonScript
from tests.api.helpers import auth, family_with_device, register, upload_lesson
from tests.api.test_sessions import now, play  # noqa: F401  (fixture)

PARIS = ZoneInfo("Europe/Paris")


def script(name: str) -> LessonScript:
    return LessonScript.from_file(REFERENCE_LESSONS / f"{name}.json")


async def two_lessons(
    client: AsyncClient, fake_llm: FakeProvider, clock: list[datetime]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Emma, sa leçon d'histoire, puis (une minute plus tard) sa leçon de fractions."""
    family = await family_with_device(client)
    fake_llm.script = script("history_cm1_revolution")
    history = await upload_lesson(client, family["device"])
    clock[0] += timedelta(minutes=1)
    fake_llm.script = script("math_cm2_fractions")
    fractions = await upload_lesson(client, family["device"])
    clock[0] -= timedelta(minutes=1)  # les jetons émis ensuite ne doivent pas dater du futur
    return family, history, fractions


async def test_daily_minutes_and_priority_subject(
    client: AsyncClient,
    db: AsyncSession,
    fake_llm: FakeProvider,
    now: list[datetime],  # noqa: F811
) -> None:
    family, history, fractions = await two_lessons(client, fake_llm, now)
    parent, token, child_id = family["parent"], family["device"], family["child"]["id"]
    url = f"/v1/children/{child_id}"

    # La dernière leçon ajoutée d'abord… sauf si le parent a choisi une matière.
    mission = (await client.get("/v1/me/mission", headers=auth(token))).json()
    assert mission["lesson"]["id"] == fractions["id"] and mission["daily_minutes"] is None
    r = await client.patch(
        url, json={"priority_subject": "history", "daily_minutes": 5}, headers=auth(parent)
    )
    assert r.status_code == 200, r.text
    assert (r.json()["priority_subject"], r.json()["daily_minutes"]) == ("history", 5)
    mission = (await client.get("/v1/me/mission", headers=auth(token))).json()
    assert mission["lesson"]["id"] == history["id"] and mission["daily_minutes"] == 5

    # 5 minutes : une séance courte (1 activité d'approfondissement, complétée jusqu'à 5 minutes,
    # règles 1.10.0) ; 20 minutes : bien plus.
    short = (await client.post(f"/v1/lessons/{history['id']}/sessions", json={}, headers=auth(token))).json()
    assert 5 <= short["estimated_duration_min"] <= 10
    await client.patch(url, json={"daily_minutes": 20}, headers=auth(parent))
    await play(client, db, token, short["id"], short["items"], lambda _: True)
    await client.post(f"/v1/sessions/{short['id']}/complete", headers=auth(token))
    long = (await client.post(f"/v1/lessons/{fractions['id']}/sessions", json={}, headers=auth(token))).json()
    assert sum(1 for i in long["items"] if i["block"] == "core") > 3
    assert long["estimated_duration_min"] > short["estimated_duration_min"]

    reset = await client.patch(
        url, json={"priority_subject": None, "daily_minutes": None}, headers=auth(parent)
    )
    assert (reset.json()["priority_subject"], reset.json()["daily_minutes"]) == (None, None)
    for bad in ({"daily_minutes": 7}, {"priority_subject": "danse"}):
        assert (await client.patch(url, json=bad, headers=auth(parent))).status_code == 422


async def test_exam_plan_drives_the_mission(
    client: AsyncClient,
    db: AsyncSession,
    fake_llm: FakeProvider,
    now: list[datetime],  # noqa: F811
) -> None:
    family, _, fractions = await two_lessons(client, fake_llm, now)
    today = now[0].astimezone(PARIS).date()

    def day(offset: int) -> str:
        return (today + timedelta(days=offset)).isoformat()

    parent, token, child_id = family["parent"], family["device"], family["child"]["id"]
    exams_url = f"/v1/children/{child_id}/exams"

    # Contrôle de fractions dans 3 jours : diagnostic, ciblé, puis mini-contrôle la veille.
    r = await client.post(
        exams_url,
        json={"title": "Contrôle de fractions", "exam_date": day(3), "lesson_ids": [fractions["id"]]},
        headers=auth(parent),
    )
    assert r.status_code == 201, r.text
    exam = r.json()
    assert [(p["day"], p["focus"], p["done"]) for p in exam["plan"]] == [
        (day(0), "diagnostic", False),
        (day(1), "targeted", False),
        (day(2), "mock_test", False),
    ]
    assert (await client.get(exams_url, headers=auth(parent))).json() == [exam]

    # La mission du jour suit le plan, même si la leçon d'histoire est plus récente… ou non.
    mission = (await client.get("/v1/me/mission", headers=auth(token))).json()
    assert mission["reason"] == "exam" and mission["lesson"]["id"] == fractions["id"]
    assert mission["exam"] == {
        "title": "Contrôle de fractions",
        "exam_date": day(3),
        "focus": "diagnostic",
        "focus_label": "Où en es-tu ? Un tour de toute la leçon",
    }

    # Séance faite lundi : l'étape est cochée, la mission reprend son cours ordinaire.
    session = (
        await client.post(f"/v1/lessons/{fractions['id']}/sessions", json={}, headers=auth(token))
    ).json()
    await play(client, db, token, session["id"], session["items"], lambda key: key != "k4")
    await client.post(f"/v1/sessions/{session['id']}/complete", headers=auth(token))
    plan = (await client.get(exams_url, headers=auth(parent))).json()[0]["plan"]
    assert plan[0]["done"] is True
    mission = (await client.get("/v1/me/mission", headers=auth(token))).json()
    assert mission["reason"] != "exam" and mission["exam"] is None

    # Le lendemain oublié ; la veille du contrôle, il reste le mini-contrôle, sur toute la leçon.
    now[0] += timedelta(days=2)
    plan = (await client.get(exams_url, headers=auth(parent))).json()[0]["plan"]
    assert [(p["day"], p["focus"]) for p in plan] == [(day(2), "mock_test")]
    mission = (await client.get("/v1/me/mission", headers=auth(token))).json()
    assert mission["exam"]["focus"] == "mock_test"
    mock = (await client.post(f"/v1/lessons/{fractions['id']}/sessions", json={}, headers=auth(token))).json()
    assert "core" in {i["block"] for i in mock["items"]}

    # Le jour du contrôle : plus de plan ; le lendemain, le contrôle n'est plus listé.
    now[0] += timedelta(days=1)
    assert (await client.get(exams_url, headers=auth(parent))).json()[0]["plan"] == []
    now[0] += timedelta(days=1)
    assert (await client.get(exams_url, headers=auth(parent))).json() == []

    removed = await client.delete(f"{exams_url}/{exam['id']}", headers=auth(parent))
    assert removed.status_code == 204


async def test_exam_validation_and_separation(
    client: AsyncClient,
    fake_llm: FakeProvider,
    now: list[datetime],  # noqa: F811
) -> None:
    family, history, _ = await two_lessons(client, fake_llm, now)
    parent, token, child_id = family["parent"], family["device"], family["child"]["id"]
    url = f"/v1/children/{child_id}/exams"
    today = now[0].astimezone(PARIS).date()

    def body(**changes: Any) -> dict[str, Any]:
        return {
            "title": "Histoire",
            "exam_date": str(today + timedelta(days=3)),
            "lesson_ids": [history["id"]],
        } | changes

    for bad, code in (
        (body(exam_date=str(today)), "invalid_exam_date"),
        (body(exam_date=str(today + timedelta(days=61))), "invalid_exam_date"),
        (body(lesson_ids=["00000000-0000-0000-0000-000000000000"]), "invalid_lessons"),
    ):
        r = await client.post(url, json=bad, headers=auth(parent))
        assert r.status_code == 422 and r.json()["error"]["code"] == code
    assert (await client.post(url, json=body(title=" "), headers=auth(parent))).status_code == 422

    assert (await client.get(url, headers=auth(token))).status_code == 403  # l'enfant
    stranger = (await register(client, "autre@example.fr"))["access_token"]
    assert (await client.get(url, headers=auth(stranger))).status_code == 404
    other = await client.post(f"/v1/children/{child_id}/exams", json=body(), headers=auth(parent))
    assert other.status_code == 201
    gone = await client.delete(f"{url}/{other.json()['id']}", headers=auth(stranger))
    assert gone.status_code == 404


@pytest.mark.parametrize("count", [5])
async def test_at_most_five_exams(
    client: AsyncClient,
    fake_llm: FakeProvider,
    now: list[datetime],  # noqa: F811
    count: int,
) -> None:
    family, history, _ = await two_lessons(client, fake_llm, now)
    url = f"/v1/children/{family['child']['id']}/exams"
    day = (now[0].astimezone(PARIS).date() + timedelta(days=5)).isoformat()
    for _ in range(count):
        r = await client.post(
            url,
            json={"title": "C", "exam_date": day, "lesson_ids": [history["id"]]},
            headers=auth(family["parent"]),
        )
        assert r.status_code == 201
    r = await client.post(
        url,
        json={"title": "C", "exam_date": day, "lesson_ids": [history["id"]]},
        headers=auth(family["parent"]),
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "too_many_exams"
