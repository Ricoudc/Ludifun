"""Étape 18 : les avis des familles, envoyés depuis l'application (parent ou enfant)."""

from typing import Any

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Feedback
from tests.api.helpers import add_child, auth, family_with_device, register, upload_lesson


async def send(client: AsyncClient, token: str, body: dict[str, Any], expected: int = 201) -> Any:
    r = await client.post("/v1/feedback", json=body, headers=auth(token))
    assert r.status_code == expected, r.text
    return r.json()


async def test_child_rates_a_session(client: AsyncClient, db: AsyncSession) -> None:
    family = await family_with_device(client)
    lesson = await upload_lesson(client, family["device"])
    session = (
        await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(family["device"]))
    ).json()
    await send(client, family["device"], {"rating": 5, "screen": "report", "session_id": session["id"]})

    row = await db.scalar(select(Feedback))
    assert row is not None
    assert (row.author, row.rating, row.screen, str(row.child_id)) == (
        "child",
        5,
        "report",
        family["child"]["id"],
    )
    assert row.parent_id is None and str(row.session_id) == session["id"]


async def test_parent_writes_a_message(client: AsyncClient, db: AsyncSession) -> None:
    family = await family_with_device(client)
    await send(client, family["parent"], {"rating": 4, "message": "  Emma adore les défis.  "})
    await send(client, family["parent"], {"message": "Et pour Emma ?", "child_id": family["child"]["id"]})

    rows = list(await db.scalars(select(Feedback).order_by(Feedback.created_at)))
    assert [(r.author, r.message) for r in rows] == [
        ("parent", "Emma adore les défis."),
        ("parent", "Et pour Emma ?"),
    ]
    assert rows[0].child_id is None and str(rows[1].child_id) == family["child"]["id"]


async def test_invalid_feedback_is_refused(client: AsyncClient) -> None:
    family = await family_with_device(client)
    parent, device = family["parent"], family["device"]
    for body in (
        {},
        {"message": "   "},
        {"rating": 0},
        {"rating": 6},
        {"message": "x" * 1001},
        {"rating": 3, "screen": "Rapport!"},
        {"rating": 3, "extra": 1},
    ):
        await send(client, parent, body, 422)
    # L'enfant ne parle que de ses propres séances ; le parent ne donne pas de séance.
    await send(client, parent, {"rating": 3, "session_id": "00000000-0000-0000-0000-000000000000"}, 422)
    await send(client, device, {"rating": 3, "session_id": "00000000-0000-0000-0000-000000000000"}, 404)
    await send(client, device, {"rating": 3, "child_id": "00000000-0000-0000-0000-000000000000"}, 404)
    await send(client, device, {"rating": 3, "child_id": family["child"]["id"]})
    assert (await client.post("/v1/feedback", json={"rating": 3})).status_code == 401


async def test_other_family_cannot_attach_feedback(client: AsyncClient) -> None:
    emma = await family_with_device(client)
    other = (await register(client, "autre@example.fr"))["access_token"]
    await send(client, other, {"rating": 2, "child_id": emma["child"]["id"]}, 404)

    other_device = (await family_with_device(client, "tiers@example.fr"))["device"]
    lesson = await upload_lesson(client, emma["device"])
    session = (
        await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(emma["device"]))
    ).json()
    await send(client, other_device, {"rating": 2, "session_id": session["id"]}, 404)


async def test_feedback_is_exported_and_deleted_with_its_author(
    client: AsyncClient, db: AsyncSession
) -> None:
    family = await family_with_device(client)
    hugo = await add_child(client, family["parent"], "Hugo", "CE2")
    await send(client, family["device"], {"rating": 1, "screen": "report"})
    await send(client, family["parent"], {"message": "Pour Hugo", "child_id": hugo["id"]})

    export = (
        await client.get(f"/v1/children/{family['child']['id']}/export", headers=auth(family["parent"]))
    ).json()
    assert [(f["author"], f["rating"]) for f in export["feedback"]] == [("child", 1)]

    r = await client.delete(f"/v1/children/{family['child']['id']}", headers=auth(family["parent"]))
    assert r.status_code == 204
    assert await db.scalar(select(func.count()).select_from(Feedback)) == 1  # celui du parent reste
    r = await client.delete("/v1/parent", headers=auth(family["parent"]))
    assert r.status_code == 204
    assert await db.scalar(select(func.count()).select_from(Feedback)) == 0
