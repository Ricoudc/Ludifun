"""Étapes 27 et 28 : images de la leçon et de ses notions, préparées sur le PC après l'analyse,
validées par le parent.

L'enfant ne voit qu'une image validée ; le parent la refuse et peut la faire refaire avec une
remarque. Une image jugée « pas utile » n'est pas dessinée. Les images validées des notions
nourrissent les jeux « apprendre par l'image ». Un autre parent ne voit rien ; supprimer la
leçon efface les fichiers.
"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.fake import FakeProvider
from app.config import Settings
from app.db.models import AiRun
from tests.api.helpers import auth, family_with_device, upload_lesson


def files(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


@pytest.fixture
def images(app: FastAPI, tmp_path: Path) -> Path:
    settings: Settings = app.state.settings
    app.state.settings = settings.model_copy(update={"image_engine": "fake", "media_dir": str(tmp_path)})
    return tmp_path


async def test_without_engine_nothing_changes(client: AsyncClient) -> None:
    family = await family_with_device(client)
    lesson = await upload_lesson(client, family["device"])
    assert lesson["status"] == "ready" and lesson["image"] is None
    url = f"/v1/children/{family['child']['id']}/lessons/{lesson['id']}/image"
    r = await client.get(url, headers=auth(family["parent"]))
    assert r.json() == {"available": False, "image": None, "pictures": []}
    r = await client.post(f"{url}/redo", json={}, headers=auth(family["parent"]))
    assert r.status_code == 503 and r.json()["error"]["code"] == "images_unavailable"


async def test_parent_validates_before_the_child_sees_it(
    client: AsyncClient, db: AsyncSession, images: Path, fake_llm: FakeProvider
) -> None:
    family = await family_with_device(client)
    parent, device = auth(family["parent"]), auth(family["device"])
    lesson = await upload_lesson(client, family["device"])
    base = f"/v1/children/{family['child']['id']}/lessons/{lesson['id']}/image"

    # Prête, mais en attente du parent : l'enfant ne la voit pas.
    state = (await client.get(base, headers=parent)).json()
    assert state["available"] is True
    image = state["image"]
    assert image["status"] == "to_review" and image["alt"] and image["url"] == f"{base}/file"
    assert image["knowledge_id"] is None and image["label"] is None
    assert lesson["image"] is None
    assert (await client.get(f"/v1/lessons/{lesson['id']}/image", headers=device)).status_code == 404
    file = await client.get(image["url"], headers=parent)
    assert file.status_code == 200 and file.headers["content-type"] == "image/png"
    assert file.content.startswith(b"\x89PNG") and len(files(images)) == 4  # la leçon et 3 notions
    runs = list(await db.scalars(select(AiRun).where(AiRun.stage == "illustration")))
    assert [r.status for r in runs] == ["ok"]

    # Validée : l'enfant la voit avec sa leçon.
    assert (await client.post(f"{base}/approve", headers=parent)).json()["status"] == "approved"
    shown = (await client.get(f"/v1/lessons/{lesson['id']}", headers=device)).json()["image"]
    assert shown == {"url": f"/v1/lessons/{lesson['id']}/image", "alt": image["alt"]}
    child_file = await client.get(shown["url"], headers=device)
    assert child_file.status_code == 200 and child_file.content == file.content

    # Refusée : plus montrée ; refaite avec une remarque, elle attend de nouveau le parent.
    assert (await client.post(f"{base}/reject", headers=parent)).json()["status"] == "rejected"
    assert (await client.get(f"/v1/lessons/{lesson['id']}", headers=device)).json()["image"] is None
    redo = await client.post(
        f"{base}/redo", json={"remark": "Plus simple, <sans> personnages"}, headers=parent
    )
    assert redo.status_code == 202
    again = (await client.get(base, headers=parent)).json()["image"]
    assert again["status"] == "to_review" and again["remark"] == "Plus simple, ‹sans› personnages"
    assert "<remarque_parent>\nPlus simple, ‹sans› personnages" in fake_llm.calls[-1][1]
    assert len(files(images)) == 4  # l'image refusée est effacée
    assert (await client.get(f"/v1/lessons/{lesson['id']}/image", headers=device)).status_code == 404

    # Supprimer la leçon efface le fichier.
    assert (
        await client.delete(
            f"/v1/lessons/{lesson['id']}", headers=parent, params={"child_id": family["child"]["id"]}
        )
    ).status_code == 204
    assert files(images) == []


async def test_only_the_family_sees_the_image(client: AsyncClient, images: Path) -> None:
    family = await family_with_device(client)
    other = await family_with_device(client, "autre@example.fr")
    lesson = await upload_lesson(client, family["device"])
    mine = f"/v1/children/{family['child']['id']}/lessons/{lesson['id']}/image"
    for path in (mine, f"{mine}/file"):
        assert (await client.get(path, headers=auth(other["parent"]))).status_code == 404
    for action in ("approve", "reject", "redo"):
        assert (
            await client.post(f"{mine}/{action}", json={}, headers=auth(other["parent"]))
        ).status_code == 404
    # Le parent valide ; l'appareil d'un autre enfant ne la voit pas pour autant.
    await client.post(f"{mine}/approve", headers=auth(family["parent"]))
    r = await client.get(f"/v1/lessons/{lesson['id']}/image", headers=auth(other["device"]))
    assert r.status_code == 404
    # L'enfant n'a pas accès aux routes du parent.
    assert (await client.post(f"{mine}/approve", headers=auth(family["device"]))).status_code == 403


async def test_a_refused_scene_gives_no_image(
    client: AsyncClient, images: Path, fake_llm: FakeProvider
) -> None:
    from app.ai.schemas import IllustrationOutput

    fake_llm.overrides["illustration"] = lambda attempt, text: IllustrationOutput(
        scene='A blackboard with "7 x 8 = 56" written on it', alt="Un tableau."
    )
    family = await family_with_device(client)
    lesson = await upload_lesson(client, family["device"])
    url = f"/v1/children/{family['child']['id']}/lessons/{lesson['id']}/image"
    image = (await client.get(url, headers=auth(family["parent"]))).json()["image"]
    assert image["status"] == "failed" and "texte" in image["error"] and image["url"] is None
    assert lesson["status"] == "ready"  # la leçon, elle, est intacte
    assert files(images) == []


async def test_pictures_of_the_notions_feed_the_picture_games(
    client: AsyncClient, db: AsyncSession, images: Path, fake_llm: FakeProvider
) -> None:
    """Étape 28 : une image par notion concrète ; validées, elles servent au jeu « Image et mot »
    et s'affichent avec les notions de la leçon ; refusées, jamais."""
    family = await family_with_device(client)
    parent, device = auth(family["parent"]), auth(family["device"])
    lesson = await upload_lesson(client, family["device"])
    base = f"/v1/children/{family['child']['id']}/lessons/{lesson['id']}"
    pictures = (await client.get(f"{base}/image", headers=parent)).json()["pictures"]
    assert [p["status"] for p in pictures] == ["to_review"] * 3
    assert all(p["label"] and p["alt"] and p["knowledge_id"] for p in pictures)
    first = pictures[0]
    assert first["url"] == f"{base}/images/{first['id']}/file"
    assert (await client.get(first["url"], headers=parent)).status_code == 200
    child_url = f"/v1/lessons/{lesson['id']}/images/{first['id']}"
    assert (await client.get(child_url, headers=device)).status_code == 404  # pas encore validée

    # En attente du parent : ni dans la leçon, ni dans les jeux.
    shown = (await client.get(f"/v1/lessons/{lesson['id']}", headers=device)).json()
    assert all(k["image"] is None for k in shown["knowledge"])

    for picture in pictures:
        r = await client.post(f"{base}/images/{picture['id']}/approve", headers=parent)
        assert r.json()["status"] == "approved"
    shown = (await client.get(f"/v1/lessons/{lesson['id']}", headers=device)).json()
    with_image = {k["id"]: k["image"] for k in shown["knowledge"] if k["image"]}
    assert set(with_image) == {p["knowledge_id"] for p in pictures}
    assert child_url in with_image.values()
    assert (await client.get(child_url, headers=device)).status_code == 200

    # Première séance : le jeu de fin est « Image et mot », sans rien qui donne la réponse.
    session = (await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=device)).json()
    game = next(i for i in session["items"] if i["block"] == "match")
    assert game["type"] == "PICTURE_MATCH"
    assert {p["image"] for p in game["payload"]["pictures"]} == set(with_image.values())
    assert set(game["payload"]) == {"prompt", "pictures", "words"}
    assert all(set(p) == {"id", "image"} for p in game["payload"]["pictures"])

    # Refusée puis refaite : de nouveau en attente, et plus montrée à l'enfant.
    assert (await client.post(f"{base}/images/{first['id']}/reject", headers=parent)).json()[
        "status"
    ] == "rejected"
    assert (await client.get(child_url, headers=device)).status_code == 404
    redo = await client.post(
        f"{base}/images/{first['id']}/redo", json={"remark": "Plus grand"}, headers=parent
    )
    assert redo.status_code == 202
    again = next(
        p
        for p in (await client.get(f"{base}/image", headers=parent)).json()["pictures"]
        if p["id"] == first["id"]
    )
    assert again["status"] == "to_review" and again["remark"] == "Plus grand"
    assert "<cible>N" in fake_llm.calls[-1][1]
    assert len(files(images)) == 4


async def test_an_image_that_would_not_help_is_not_drawn(
    client: AsyncClient, images: Path, fake_llm: FakeProvider
) -> None:
    """L'IA juge qu'une image n'aiderait pas (une règle de conjugaison) : rien n'est dessiné, le
    parent voit pourquoi, et peut en demander une quand même."""
    from app.ai.schemas import IllustrationOutput

    fake_llm.overrides["illustration"] = lambda attempt, text: (
        IllustrationOutput(scene="A cosy library with books", alt="Une bibliothèque.")
        if "<cible>" in text
        else IllustrationOutput(useful=False, why="Une règle de conjugaison ne se dessine pas.")
    )
    family = await family_with_device(client)
    lesson = await upload_lesson(client, family["device"])
    url = f"/v1/children/{family['child']['id']}/lessons/{lesson['id']}/image"
    state = (await client.get(url, headers=auth(family["parent"]))).json()
    assert state["pictures"] == []
    image = state["image"]
    assert image["status"] == "not_needed" and image["url"] is None
    assert image["error"] == "Une règle de conjugaison ne se dessine pas."
    assert files(images) == []
    # Le parent insiste : elle est faite (la cible dit à l'IA de la proposer).
    assert (await client.post(f"{url}/redo", json={}, headers=auth(family["parent"]))).status_code == 202
    image = (await client.get(url, headers=auth(family["parent"]))).json()["image"]
    assert image["status"] == "to_review" and len(files(images)) == 1


async def test_images_can_be_prepared_for_an_older_lesson(
    client: AsyncClient, app: FastAPI, tmp_path: Path
) -> None:
    """Leçon analysée sans moteur d'images ; le moteur installé, le parent les fait préparer."""
    family = await family_with_device(client)
    lesson = await upload_lesson(client, family["device"])
    settings: Settings = app.state.settings
    app.state.settings = settings.model_copy(update={"image_engine": "fake", "media_dir": str(tmp_path)})
    base = f"/v1/children/{family['child']['id']}/lessons/{lesson['id']}"
    assert (await client.get(f"{base}/image", headers=auth(family["parent"]))).json()["image"] is None
    r = await client.post(f"{base}/images/prepare", headers=auth(family["parent"]))
    assert r.status_code == 202
    state = (await client.get(f"{base}/image", headers=auth(family["parent"]))).json()
    assert state["image"]["status"] == "to_review" and len(state["pictures"]) == 3
    assert len(files(tmp_path)) == 4
