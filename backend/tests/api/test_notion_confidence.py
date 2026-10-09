"""Confiance des notions (§115) : une notion douteuse n'est pas proposée à l'enfant avant que le
parent l'ait confirmée ; le parent voit pourquoi elle est douteuse."""

import uuid

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import KnowledgeItem
from tests.api.helpers import auth, family_with_device, upload_lesson


async def test_a_doubtful_notion_waits_for_the_parent(client: AsyncClient, db: AsyncSession) -> None:
    family = await family_with_device(client)
    token, parent, child_id = family["device"], family["parent"], family["child"]["id"]
    lesson = await upload_lesson(client, token)
    # Une leçon bien lue : tout est en confiance élevée.
    content_url = f"/v1/children/{child_id}/lessons/{lesson['id']}/content"
    notions = (await client.get(content_url, headers=auth(parent))).json()["notions"]
    assert {n["trust"] for n in notions} == {"high"}
    assert (await client.get("/v1/lessons", headers=auth(token))).json()[0]["notions_to_check"] == 0

    k1 = next(k["id"] for k in lesson["knowledge"] if k["label"] == "1789")
    await db.execute(
        update(KnowledgeItem)
        .where(KnowledgeItem.id == uuid.UUID(k1))
        .values(confidence=0.3, doubts=["la page a été mal lue", "un mot du passage était illisible"])
    )
    await db.commit()
    assert (await client.get("/v1/lessons", headers=auth(token))).json()[0]["notions_to_check"] == 1
    notion = next(
        n
        for n in (await client.get(content_url, headers=auth(parent))).json()["notions"]
        if n["knowledge_id"] == k1
    )
    assert notion["trust"] == "low" and notion["doubts"][0] == "la page a été mal lue"

    # Pas proposée à l'enfant tant que le parent ne l'a pas confirmée.
    session = (await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))).json()
    assert all(k1 not in item["knowledge_ids"] for item in session["items"])

    r = await client.post(
        f"/v1/children/{child_id}/lessons/{lesson['id']}/notions/{k1}/confirm", headers=auth(parent)
    )
    assert r.status_code == 200 and r.json()["confirmed"] is True
    assert (await client.get("/v1/lessons", headers=auth(token))).json()[0]["notions_to_check"] == 0
    # L'appareil de l'enfant ne peut pas confirmer à la place du parent.
    r = await client.post(
        f"/v1/children/{child_id}/lessons/{lesson['id']}/notions/{k1}/confirm", headers=auth(token)
    )
    assert r.status_code == 403
