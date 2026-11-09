"""Relecture par le parent avant l'enfant (§5.69) : l'IA peut se tromper.

- case « Je relis chaque leçon avant mon enfant » cochée par défaut : une leçon prête attend la
  validation du parent ; l'enfant ne peut ni l'ouvrir, ni la réviser, ni l'expliquer à Ludi ;
- le parent voit toute la leçon, corrige le titre, le résumé, le nom et la phrase « à retenir »
  d'une notion, retire une notion fausse (jamais la dernière), puis valide ;
- décocher la case ouvre aussitôt les leçons en attente.
"""

import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import KnowledgeMaterial
from tests.api.helpers import auth, family_with_device, upload_lesson


def content_url(family: dict[str, Any], lesson: dict[str, Any], end: str = "content") -> str:
    return f"/v1/children/{family['child']['id']}/lessons/{lesson['id']}/{end}"


async def test_the_child_waits_until_the_parent_approves(client: AsyncClient) -> None:
    family = await family_with_device(client, review_lessons=True)
    device, parent = auth(family["device"]), auth(family["parent"])
    assert (await client.get("/v1/parent/review-lessons", headers=parent)).json() == {"enabled": True}

    lesson = await upload_lesson(client, family["device"])
    assert lesson["status"] == "ready" and lesson["awaiting_parent"] is True
    assert lesson["knowledge"] == [] and lesson["skills"] == []  # rien de la leçon avant la relecture
    listed = (await client.get("/v1/lessons", headers=device)).json()
    assert listed[0]["awaiting_parent"] is True
    blocked = await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=device)
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "lesson_awaiting_parent"
    assert "adulte" in blocked.json()["error"]["message"]
    for url in (f"/v1/lessons/{lesson['id']}/sheet",):
        r = await client.get(url, headers=device)
        assert r.status_code == 409 and r.json()["error"]["code"] == "lesson_awaiting_parent"
    teach = await client.post(f"/v1/lessons/{lesson['id']}/teach", json={}, headers=device)
    assert teach.status_code == 409
    mission = (await client.get("/v1/me/mission", headers=device)).json()
    assert mission["lesson"] is None  # pas de mission sur une leçon pas encore relue

    # Le parent voit toute la leçon.
    content = (await client.get(content_url(family, lesson), headers=parent)).json()
    assert content["awaiting_parent"] is True and content["approved"] is False
    assert content["summary"] and content["objective"] and len(content["notions"]) >= 3
    first, second = content["notions"][0], content["notions"][1]

    # Il corrige le titre et le résumé, une notion, et en retire une autre.
    info = {"title": "La Révolution de 1789", "objective": "Connaître 1789", "summary": "Un résumé juste."}
    r = await client.put(content_url(family, lesson, "info"), json=info, headers=parent)
    assert r.status_code == 200 and r.json()["title"] == "La Révolution de 1789"
    notion = content_url(family, lesson, f"notions/{first['knowledge_id']}")
    fixed = {"label": "1789", "statement": "La Révolution commence en 1789."}
    r = await client.put(notion + "/text", json=fixed, headers=parent)
    assert r.status_code == 200 and r.json()["statement"] == fixed["statement"]
    removed = content_url(family, lesson, f"notions/{second['knowledge_id']}")
    r = await client.post(removed + "/remove", headers=parent)
    assert r.status_code == 200 and r.json()["removed"] is True

    # Il valide : l'enfant ouvre la leçon corrigée, sans la notion retirée, et la révise.
    approved = await client.post(content_url(family, lesson, "approve"), headers=parent)
    assert approved.status_code == 200 and approved.json()["approved"] is True
    opened = (await client.get(f"/v1/lessons/{lesson['id']}", headers=device)).json()
    assert opened["awaiting_parent"] is False and opened["title"] == "La Révolution de 1789"
    assert opened["summary"] == "Un résumé juste."
    ids = {k["id"] for k in opened["knowledge"]}
    assert second["knowledge_id"] not in ids and first["knowledge_id"] in ids
    assert (
        next(k for k in opened["knowledge"] if k["id"] == first["knowledge_id"])["statement"]
        == (fixed["statement"])
    )
    session = await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=device)
    assert session.status_code == 200, session.text
    played = {k for item in session.json()["items"] for k in item.get("knowledge_ids", [])}
    assert second["knowledge_id"] not in played

    # « Remettre » la rend de nouveau ; le parent la voit toujours, marquée.
    r = await client.post(removed + "/restore", headers=parent)
    assert r.status_code == 200 and r.json()["removed"] is False


async def test_the_last_notion_cannot_be_removed(client: AsyncClient) -> None:
    family = await family_with_device(client, review_lessons=True)
    parent = auth(family["parent"])
    lesson = await upload_lesson(client, family["device"])
    notions = (await client.get(content_url(family, lesson), headers=parent)).json()["notions"]
    for notion in notions[:-1]:
        url = content_url(family, lesson, f"notions/{notion['knowledge_id']}/remove")
        assert (await client.post(url, headers=parent)).status_code == 200
    last = content_url(family, lesson, f"notions/{notions[-1]['knowledge_id']}/remove")
    r = await client.post(last, headers=parent)
    assert r.status_code == 409 and r.json()["error"]["code"] == "last_notion"


async def test_unchecking_the_box_opens_waiting_lessons(client: AsyncClient) -> None:
    family = await family_with_device(client, review_lessons=True)
    lesson = await upload_lesson(client, family["device"])
    assert lesson["awaiting_parent"] is True
    r = await client.put("/v1/parent/review-lessons", json={"enabled": False}, headers=auth(family["parent"]))
    assert r.status_code == 200 and r.json() == {"enabled": False}
    opened = (await client.get(f"/v1/lessons/{lesson['id']}", headers=auth(family["device"]))).json()
    assert opened["awaiting_parent"] is False and opened["knowledge"]
    content = (await client.get(content_url(family, lesson), headers=auth(family["parent"]))).json()
    assert content["approved"] is False and content["awaiting_parent"] is False


async def test_bad_edits_are_refused(client: AsyncClient) -> None:
    family = await family_with_device(client, review_lessons=True)
    parent = auth(family["parent"])
    lesson = await upload_lesson(client, family["device"])
    empty = {"title": " ", "objective": "", "summary": "x"}
    assert (
        await client.put(content_url(family, lesson, "info"), json=empty, headers=parent)
    ).status_code == 422
    other = "00000000-0000-4000-8000-000000000009"
    url = content_url(family, lesson, f"notions/{other}/text")
    r = await client.put(url, json={"label": "a", "statement": "b"}, headers=parent)
    assert r.status_code == 404


async def test_correcting_a_word_to_write_corrects_the_spelling_games(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Mot de liste mal lu (« hopital ») : le parent corrige le nom, et c'est « hôpital » que les
    jeux d'écriture (§5.68) font écrire."""
    family = await family_with_device(client, review_lessons=True)
    lesson = await upload_lesson(client, family["device"])
    notion = (await client.get(content_url(family, lesson), headers=auth(family["parent"]))).json()[
        "notions"
    ][0]
    row = await db.get(KnowledgeMaterial, uuid.UUID(notion["knowledge_id"]))
    assert row is not None
    row.material = {**row.material, "spelling": {"word": notion["label"], "sentence": None}}
    await db.commit()
    url = content_url(family, lesson, f"notions/{notion['knowledge_id']}/text")
    r = await client.put(
        url, json={"label": "hôpital", "statement": "On soigne à l'hôpital."}, headers=auth(family["parent"])
    )
    assert r.status_code == 200, r.text
    await db.refresh(row)
    assert row.material["spelling"]["word"] == "hôpital"
