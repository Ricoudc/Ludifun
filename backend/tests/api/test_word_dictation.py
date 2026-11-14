"""§5.99 : dictée à partir d'une liste de mots, prête tout de suite et sans IA."""

from httpx import AsyncClient

from app.ai.providers.fake import FakeProvider
from tests.api.helpers import auth, family_with_device, register

WORDS = "chaton : Le chaton dort sur le lit.\nmaison\nécole : Je vais à l'école.\naujourd'hui"
WRITING = {"WORD_FLASH", "SCRAMBLE", "DICTATION", "SENTENCE_DICTATION", "MCQ", "FILL_BLANK"}


async def test_the_parent_types_a_list_and_the_child_revises_it(
    client: AsyncClient, fake_llm: FakeProvider
) -> None:
    family = await family_with_device(client, review_lessons=True)  # la famille relit les leçons
    child = family["child"]["id"]
    r = await client.post(
        "/v1/lessons/words",
        json={"text": WORDS, "title": "Mots de la semaine"},
        params={"child_id": child},
        headers=auth(family["parent"]),
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "ready"
    assert fake_llm.calls == []  # aucune IA

    lesson = (await client.get(f"/v1/lessons/{r.json()['id']}", headers=auth(family["device"]))).json()
    assert lesson["title"] == "Dictée : Mots de la semaine" and lesson["subject"] == "french"
    assert not lesson["awaiting_parent"]  # tapée par le parent : déjà validée
    device = auth(family["device"])
    session = await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=device)
    assert session.status_code in (200, 201), session.text
    types = {i["type"] for i in session.json()["items"]}
    assert types and types <= WRITING, types


async def test_typed_by_the_child_it_waits_for_the_parent(client: AsyncClient) -> None:
    family = await family_with_device(client, review_lessons=True)
    r = await client.post("/v1/lessons/words", json={"text": WORDS}, headers=auth(family["device"]))
    assert r.status_code == 201, r.text
    lesson = (await client.get(f"/v1/lessons/{r.json()['id']}", headers=auth(family["device"]))).json()
    assert lesson["awaiting_parent"]


async def test_a_wrong_list_says_which_line(client: AsyncClient) -> None:
    family = await family_with_device(client)
    wrong = {"text": "chaton\nlapin : Le chat mange.\nmaison"}
    r = await client.post("/v1/lessons/words", json=wrong, headers=auth(family["device"]))
    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "word_list_invalid"
    assert error["message"] == "Ligne 2 : la phrase ne contient pas le mot « lapin »."


async def test_another_family_cannot_add_a_list(client: AsyncClient) -> None:
    family = await family_with_device(client)
    stranger = (await register(client, "autre@example.fr"))["access_token"]
    r = await client.post(
        "/v1/lessons/words",
        json={"text": WORDS},
        params={"child_id": family["child"]["id"]},
        headers=auth(stranger),
    )
    assert r.status_code == 404
