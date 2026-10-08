"""Mode devoirs (§29, §127) : l'enfant est guidé pas à pas, la réponse n'arrive jamais d'emblée ;
le parent voit l'aide utilisée. IA factice : soustraction quand l'énoncé parle de donner."""

from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AiRun
from app.domain.homework import ATTEMPTS_BEFORE_SOLUTION
from tests.api.helpers import PHOTO, auth, family_with_device

BILLES = "Paul a 24 billes. Il en donne 16 à Léa. Combien de billes lui reste-t-il ?"


async def start(client: AsyncClient, token: str, text: str = BILLES) -> dict[str, Any]:
    r = await client.post("/v1/homework/text", json={"text": text}, headers=auth(token))
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "preparing"
    # La préparation (IA factice) tourne en tâche de fond avant la fin de la requête de test.
    ready: dict[str, Any] = (await client.get(f"/v1/homework/{r.json()['id']}", headers=auth(token))).json()
    return ready


async def test_the_child_is_guided_step_by_step(client: AsyncClient, db: AsyncSession) -> None:
    family = await family_with_device(client)
    token = family["device"]
    homework = await start(client, token)
    url = f"/v1/homework/{homework['id']}"
    assert homework["status"] == "ready" and homework["statement"] == BILLES
    # D'abord « Qu'est-ce qu'on cherche ? », rien d'autre ; la réponse n'est nulle part.
    assert [s["kind"] for s in homework["steps"]] == ["task"]
    assert homework["steps"][0]["title"] == "🔎 Qu'est-ce qu'on cherche ?"
    assert homework["answer"] is None and homework["solution"] is None
    assert homework["steps_left"] == 4  # l'étape qui donnait « 8 » a été retirée
    assert "8" not in str(homework["steps"])

    # Pas de correction avant d'avoir essayé.
    r = await client.post(f"{url}/solution", headers=auth(token))
    assert r.status_code == 409 and r.json()["error"]["code"] == "solution_not_yet"

    # Les étapes, une par une, dans l'ordre du §127.
    kinds = []
    for _ in range(4):
        r = await client.post(f"{url}/next-step", headers=auth(token))
        assert r.status_code == 200
        kinds.append(r.json()["steps"][-1]["kind"])
    assert kinds == ["hint", "question", "reminder", "method"]
    assert all("8" not in s["text"] for s in r.json()["steps"])
    r = await client.post(f"{url}/next-step", headers=auth(token))
    assert r.status_code == 409 and r.json()["error"]["code"] == "no_more_steps"

    # Des essais faux, puis la correction guidée.
    for wrong in ["40", "10"][:ATTEMPTS_BEFORE_SOLUTION]:
        r = await client.post(f"{url}/attempts", json={"text": wrong}, headers=auth(token))
        assert r.status_code == 200 and r.json()["attempts"][-1]["correct"] is False
    assert r.json()["solution_available"] is True and r.json()["answer"] is None
    guided = (await client.post(f"{url}/solution", headers=auth(token))).json()
    assert guided["status"] == "guided" and guided["answer"] == "8"
    assert guided["solution"][0] == "24 − 16 = 8"
    r = await client.post(f"{url}/attempts", json={"text": "8"}, headers=auth(token))
    assert r.status_code == 409  # terminé

    # Le journal de l'IA note l'étape écartée, sans lien avec une leçon.
    run = await db.scalar(select(AiRun).where(AiRun.stage == "homework"))
    assert run is not None and run.lesson_id is None
    assert any("donnerait la réponse" in w for w in run.warnings)


async def test_solved_alone_and_seen_by_the_parent(client: AsyncClient) -> None:
    family = await family_with_device(client)
    token, parent = family["device"], auth(family["parent"])
    first = await start(client, token)
    r = await client.post(
        f"/v1/homework/{first['id']}/attempts", json={"text": "Il reste 8 billes."}, headers=auth(token)
    )
    solved = r.json()
    assert solved["status"] == "solved" and solved["answer"] == "8"
    assert solved["check"] == "Refais l'opération à l'envers pour vérifier."

    second = await start(client, token, "Léa a 12 images. Elle en reçoit 5. Combien en a-t-elle en tout ?")
    await client.post(f"/v1/homework/{second['id']}/next-step", headers=auth(token))
    r = await client.post(
        f"/v1/homework/{second['id']}/attempts", json={"text": "dix-sept"}, headers=auth(token)
    )
    assert r.json()["status"] == "solved"

    listed = (await client.get(f"/v1/children/{family['child']['id']}/homework", headers=parent)).json()
    assert [h["id"] for h in listed["homework"]] == [second["id"], first["id"]]
    newest, oldest = listed["homework"]
    assert oldest["solved_alone"] is True and oldest["steps_used"] == 0 and oldest["attempts"] == 1
    assert newest["solved_alone"] is False and newest["steps_used"] == 1 and newest["steps_total"] == 4

    export = (await client.get(f"/v1/children/{family['child']['id']}/export", headers=parent)).json()
    assert [h["status"] for h in export["homework"]] == ["solved", "solved"]
    assert export["homework"][0]["statement"] == BILLES

    # Un autre enfant, un autre parent : rien.
    other = await family_with_device(client, "autre@example.fr")
    assert (await client.get(f"/v1/homework/{first['id']}", headers=auth(other["device"]))).status_code == 404
    r = await client.post(f"/v1/homework/{first['id']}/next-step", headers=auth(other["device"]))
    assert r.status_code == 404
    r = await client.get(f"/v1/children/{family['child']['id']}/homework", headers=auth(other["parent"]))
    assert r.status_code == 404


async def test_a_photo_is_read_then_forgotten(client: AsyncClient) -> None:
    family = await family_with_device(client)
    token = family["device"]
    r = await client.post(
        "/v1/homework", files=[("pages", ("exo.jpg", PHOTO, "image/jpeg"))], headers=auth(token)
    )
    assert r.status_code == 202, r.text
    homework = (await client.get(f"/v1/homework/{r.json()['id']}", headers=auth(token))).json()
    assert homework["status"] == "ready" and homework["statement"]  # le texte lu, pas la photo
    too_short = await client.post("/v1/homework/text", json={"text": "trop"}, headers=auth(token))
    assert too_short.status_code == 422
