"""« Mon cahier » : l'enfant relit ses leçons (fiche de révision, vidéos et exercices proposés)
et ses devoirs, sans faire de jeux ; jamais ceux d'un autre enfant."""

from httpx import AsyncClient

from tests.api.helpers import auth, family_with_device, upload_lesson


async def test_the_sheet_shows_what_to_remember_without_the_games(client: AsyncClient) -> None:
    family = await family_with_device(client)
    token = family["device"]
    lesson = await upload_lesson(client, token)
    r = await client.get(f"/v1/lessons/{lesson['id']}/sheet", headers=auth(token))
    assert r.status_code == 200, r.text
    sheet = r.json()
    assert sheet["title"] == lesson["title"] and sheet["objective"]
    assert "Louis XVI" in sheet["text"]  # le texte de la leçon, tel qu'il a été lu
    first = sheet["notions"][0]
    assert first["importance"] == 5 and first["statement"] and first["explanation"]
    assert first["level"] == 0
    assert {n["id"] for n in sheet["notions"]} == {k["id"] for k in lesson["knowledge"]}
    # Rien qui serve à noter un jeu : ni questions à choix, ni réponses attendues.
    assert "distractors" not in r.text and "questions" not in r.text
    assert sheet["resources"] == lesson["resources"]


async def test_the_child_finds_its_homework_again(client: AsyncClient) -> None:
    family = await family_with_device(client)
    token = family["device"]
    text = "Paul a 24 billes. Il en donne 16 à Léa. Combien lui en reste-t-il ?"
    created = (await client.post("/v1/homework/text", json={"text": text}, headers=auth(token))).json()
    r = await client.get("/v1/homework", headers=auth(token))
    assert r.status_code == 200
    listed = r.json()["homework"]
    assert [h["id"] for h in listed] == [created["id"]] and listed[0]["statement"] == text
    assert r.json()["next_before"] is None


async def test_nobody_reads_another_childs_notebook(client: AsyncClient) -> None:
    emma = await family_with_device(client, "a@example.fr")
    leo = await family_with_device(client, "b@example.fr")
    lesson = await upload_lesson(client, emma["device"])
    await client.post(
        "/v1/homework/text", json={"text": "Combien font 12 et 30 en tout ?"}, headers=auth(emma["device"])
    )
    r = await client.get(f"/v1/lessons/{lesson['id']}/sheet", headers=auth(leo["device"]))
    assert r.status_code == 404
    assert (await client.get("/v1/homework", headers=auth(leo["device"]))).json()["homework"] == []
    assert (await client.get("/v1/homework")).status_code == 401
