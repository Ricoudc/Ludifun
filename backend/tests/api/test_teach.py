"""« Enseigne-moi » (§83) : l'enfant explique une notion à Ludi, qui relance ; le code décide des
tours, des points clés retenus et du niveau « expliquer ». IA factice : les points clés dont les
mots sont dans les explications."""

import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.ai.ports import AIError
from app.ai.providers.fake import FakeProvider
from app.db.models import AiRun, KnowledgeMastery
from app.domain.teach import FOLLOW_UPS
from tests.api.helpers import auth, family_with_device, upload_lesson

FREEDOM = "Les hommes naissent libres et égaux en droits, c'est écrit dans la Déclaration."


def notion(lesson: dict[str, Any], label: str) -> str:
    found: str = next(k["id"] for k in lesson["knowledge"] if k["label"] == label)
    return found


async def explain_all(client: AsyncClient, token: str, teach: dict[str, Any], text: str) -> dict[str, Any]:
    """Explique jusqu'à la fin : jamais plus de `FOLLOW_UPS` + 1 explications en tout."""
    while teach["status"] == "open":
        assert sum(m["speaker"] == "child" for m in teach["messages"]) <= FOLLOW_UPS
        r = await client.post(f"/v1/teach/{teach['id']}/answers", json={"text": text}, headers=auth(token))
        assert r.status_code == 200, r.text
        teach = r.json()
    assert sum(m["speaker"] == "child" for m in teach["messages"]) == FOLLOW_UPS + 1
    return teach


async def test_ludi_asks_then_the_child_explains(client: AsyncClient, db: AsyncSession) -> None:
    family = await family_with_device(client)
    token = family["device"]
    lesson = await upload_lesson(client, token)
    r = await client.post(f"/v1/lessons/{lesson['id']}/teach", json={}, headers=auth(token))
    assert r.status_code == 201, r.text
    teach = r.json()
    # Notion jamais travaillée : le moteur prend la plus importante de la leçon.
    assert teach["label"] == "1789" and teach["status"] == "open" and teach["total"] == 1
    assert [m["speaker"] for m in teach["messages"]] == ["ludi"]
    # Typographie française : espaces insécables autour des guillemets.
    assert "Explique-moi «\xa01789\xa0»" in teach["messages"][0]["text"]

    r = await client.post(
        f"/v1/teach/{teach['id']}/answers",
        json={"text": "La Révolution française commence en 1789 !"},
        headers=auth(token),
    )
    first = r.json()
    assert first["status"] == "open"
    assert [m["speaker"] for m in first["messages"]] == ["ludi", "child", "ludi", "ludi"]
    assert first["messages"][-1]["text"].endswith("?")

    done = await explain_all(client, token, first, "En 1789.")
    assert done["status"] == "finished" and done["covered"] == 1
    # Notion pas encore travaillée en séance : aucun niveau n'est validé.
    assert done["validated"] is False and "tout appris" in done["summary"]
    late = await client.post(f"/v1/teach/{teach['id']}/answers", json={"text": "Encore"}, headers=auth(token))
    assert late.status_code == 409 and late.json()["error"]["code"] == "teach_finished"
    runs = await db.scalar(select(func.count()).select_from(AiRun).where(AiRun.stage == "teach"))
    assert runs == FOLLOW_UPS + 1

    # Le parent voit l'explication et la règle appliquée.
    r = await client.get(f"/v1/children/{family['child']['id']}/teach", headers=auth(family["parent"]))
    listed = r.json()["teach"]
    assert len(listed) == 1 and listed[0]["label"] == "1789" and listed[0]["covered"] == 1
    assert listed[0]["turns"][0]["answer"] == "La Révolution française commence en 1789 !"
    assert "pas encore travaillée en séance" in listed[0]["decision"]


async def test_a_good_explanation_validates_the_explain_level(client: AsyncClient, db: AsyncSession) -> None:
    family = await family_with_device(client)
    token = family["device"]
    lesson = await upload_lesson(client, token)
    k5 = notion(lesson, "Déclaration des droits de l'homme et du citoyen")
    now = clock.now()
    db.add(
        KnowledgeMastery(
            child_id=uuid.UUID(family["child"]["id"]),
            knowledge_id=uuid.UUID(k5),
            score=70,
            box=2,
            next_review_at=now,
            last_practiced_at=now,
            levels=[1, 2],
        )
    )
    await db.commit()
    r = await client.post(f"/v1/lessons/{lesson['id']}/teach", json={"knowledge_id": k5}, headers=auth(token))
    teach = r.json()
    assert teach["total"] == 2  # les points clés de la question « expliquer » de la notion
    done = await explain_all(client, token, teach, FREEDOM)
    assert done["covered"] == 2 and done["validated"] is True
    mastery = await db.scalar(
        select(KnowledgeMastery)
        .where(KnowledgeMastery.knowledge_id == uuid.UUID(k5))
        .execution_options(populate_existing=True)
    )
    assert mastery is not None and 4 in mastery.levels
    r = await client.get(f"/v1/children/{family['child']['id']}/teach", headers=auth(family["parent"]))
    assert "niveau « Expliquer » validé" in r.json()["teach"][0]["decision"]


async def test_without_ai_ludi_still_answers(client: AsyncClient, fake_llm: FakeProvider) -> None:
    family = await family_with_device(client)
    token = family["device"]
    lesson = await upload_lesson(client, token)
    fake_llm.overrides["teach"] = AIError("API 529 : overloaded")
    k5 = notion(lesson, "Déclaration des droits de l'homme et du citoyen")
    teach = (
        await client.post(f"/v1/lessons/{lesson['id']}/teach", json={"knowledge_id": k5}, headers=auth(token))
    ).json()
    r = await client.post(f"/v1/teach/{teach['id']}/answers", json={"text": FREEDOM}, headers=auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["messages"][2]["text"].startswith("Merci, je comprends un peu mieux")
    assert body["messages"][-1]["text"] == "Tu peux me donner un exemple\u202f?"
    done = await explain_all(client, token, body, "Libres et égaux.")
    assert done["covered"] == 2  # reconnus par leurs mots


async def test_a_notion_from_another_lesson_or_child_is_refused(client: AsyncClient) -> None:
    emma = await family_with_device(client, "a@example.fr")
    leo = await family_with_device(client, "b@example.fr")
    lesson = await upload_lesson(client, emma["device"])
    teach = (
        await client.post(f"/v1/lessons/{lesson['id']}/teach", json={}, headers=auth(emma["device"]))
    ).json()
    other = await upload_lesson(client, leo["device"])
    # La tablette de Léo ne voit ni la leçon ni la conversation d'Emma.
    r = await client.post(f"/v1/lessons/{lesson['id']}/teach", json={}, headers=auth(leo["device"]))
    assert r.status_code == 404
    for method, path, body in (
        ("GET", f"/v1/teach/{teach['id']}", None),
        ("POST", f"/v1/teach/{teach['id']}/answers", {"text": "Bonjour"}),
    ):
        r = await client.request(method, path, json=body, headers=auth(leo["device"]))
        assert r.status_code == 404
    # Une notion d'une autre leçon : introuvable dans celle-ci.
    r = await client.post(
        f"/v1/lessons/{lesson['id']}/teach",
        json={"knowledge_id": other["knowledge"][0]["id"]},
        headers=auth(emma["device"]),
    )
    assert r.status_code == 404 and r.json()["error"]["code"] == "knowledge_not_found"
