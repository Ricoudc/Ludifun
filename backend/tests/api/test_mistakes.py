"""Le parent voit les questions ratées : question, réponse de l'enfant, bonne réponse."""

from datetime import datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api.helpers import auth, family_with_device, register, upload_lesson
from tests.api.test_dashboard import revise
from tests.api.test_sessions import now  # noqa: F401  (fixture)


async def test_the_parent_sees_the_wrong_answers(
    client: AsyncClient,
    db: AsyncSession,
    now: list[datetime],  # noqa: F811
) -> None:
    family = await family_with_device(client)
    parent, token, child_id = family["parent"], family["device"], family["child"]["id"]
    lesson = await upload_lesson(client, token)
    url = f"/v1/children/{child_id}/mistakes"
    assert (await client.get(url, headers=auth(parent))).json() == {"mistakes": [], "next_before": None}

    await revise(client, db, token, lesson["id"], lambda key: key != "k1")
    body = (await client.get(url, headers=auth(parent))).json()
    assert body["mistakes"]
    labels = {k["label"] for k in lesson["knowledge"]}
    for mistake in body["mistakes"]:
        assert mistake["lesson_id"] == lesson["id"]
        assert mistake["question"] or mistake["activity_type"] == "MEMORY"
        assert mistake["given"] and mistake["expected"]
        assert mistake["notions"] and set(mistake["notions"]) <= labels
    answered = [m["answered_at"] for m in body["mistakes"]]
    assert answered == sorted(answered, reverse=True)

    page = (await client.get(url, params={"limit": 1}, headers=auth(parent))).json()
    assert len(page["mistakes"]) == 1 and page["next_before"] is not None

    # Réservé au parent de cet enfant.
    assert (await client.get(url, headers=auth(token))).status_code == 403
    stranger = (await register(client, "autre@example.fr"))["access_token"]
    assert (await client.get(url, headers=auth(stranger))).status_code == 404
