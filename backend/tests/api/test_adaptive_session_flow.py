"""Parcours API : les échecs d'une séance doivent abaisser la difficulté de la suivante."""

import uuid
from datetime import datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import KnowledgeItem, KnowledgeMastery, SessionItem
from tests.api.helpers import auth, family_with_device, upload_lesson
from tests.api.test_sessions import now, play  # noqa: F401  (fixture)


async def test_failed_answers_lower_the_next_session_difficulty(
    client: AsyncClient,
    db: AsyncSession,
    now: list[datetime],  # noqa: F811
) -> None:
    """Deux échecs au niveau 2 sont persistés, relus, puis appliqués à la séance suivante."""
    family = await family_with_device(client)
    token = family["device"]
    child_id = uuid.UUID(family["child"]["id"])
    lesson = await upload_lesson(client, token)
    url = f"/v1/lessons/{lesson['id']}/sessions"

    first = (await client.post(url, json={}, headers=auth(token))).json()
    notion_id = await db.scalar(select(KnowledgeItem.id).where(KnowledgeItem.key == "k1"))
    assert notion_id is not None

    # Force deux activités de cette notion au niveau 2 pour isoler la règle de baisse.
    target_items = [
        item
        for item in await db.scalars(
            select(SessionItem).where(SessionItem.session_id == uuid.UUID(first["id"]))
        )
        if notion_id in item.knowledge_ids
    ]
    assert len(target_items) >= 2
    for item in target_items[:2]:
        item.difficulty = 2
    await db.flush()

    await play(client, db, token, first["id"], first["items"], lambda key: key != "k1")
    completed = await client.post(f"/v1/sessions/{first['id']}/complete", headers=auth(token))
    assert completed.status_code == 200, completed.text

    # Maintient le score de maîtrise dans la tranche de base 2 et rend la notion révisable.
    mastery = await db.get(KnowledgeMastery, (child_id, notion_id))
    assert mastery is not None
    mastery.score = 60
    mastery.box = 2
    mastery.levels = [1, 2, 3]
    mastery.next_review_at = now[0] - timedelta(minutes=1)
    await db.flush()

    second_response = await client.post(url, json={}, headers=auth(token))
    assert second_response.status_code == 200, second_response.text
    second = second_response.json()
    assert second["kind"] == "review"

    # L'historique contient les deux échecs au niveau 2 : la préférence passe de 2 à 1.
    adapted = [item for item in second["items"] if str(notion_id) in item["knowledge_ids"]]
    assert adapted, "la notion échouée doit être retravaillée"
    assert all(item["difficulty"] == 1 for item in adapted), [
        (item["type"], item["difficulty"]) for item in adapted
    ]
