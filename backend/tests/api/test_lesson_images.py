"""Étape 27 : image de la leçon, préparée sur le PC après l'analyse, validée par le parent.

L'enfant ne voit qu'une image validée ; le parent la refuse et peut la faire refaire avec une
remarque. Un autre parent ne voit rien ; supprimer la leçon efface le fichier.
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
    assert r.json() == {"available": False, "image": None}
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
    assert lesson["image"] is None
    assert (await client.get(f"/v1/lessons/{lesson['id']}/image", headers=device)).status_code == 404
    file = await client.get(image["url"], headers=parent)
    assert file.status_code == 200 and file.headers["content-type"] == "image/png"
    assert file.content.startswith(b"\x89PNG") and len(files(images)) == 1
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
    assert len(files(images)) == 1  # l'image refusée est effacée
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
