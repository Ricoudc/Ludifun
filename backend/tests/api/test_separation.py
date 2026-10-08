"""Séparation stricte (§16.1), vérifiée route par route.

- sans jeton : 401 ;
- appareil d'un enfant sur une route parent : 403 ;
- parent d'une autre famille : 404, comme si l'enfant n'existait pas.
"""

from typing import Any

import pytest
from httpx import AsyncClient

from tests.api.helpers import add_child, auth, link_device, register

LESSON = "00000000-0000-4000-8000-000000000001"
PARENT_ROUTES = [
    ("GET", "/v1/parent", None),
    ("DELETE", "/v1/parent", None),
    ("GET", "/v1/children", None),
    ("POST", "/v1/children", {"display_name": "X", "grade": "CP", "parental_consent": True}),
    ("PATCH", "/v1/children/{child}", {"grade": "CE2"}),
    ("DELETE", "/v1/children/{child}", None),
    ("POST", "/v1/children/{child}/link-codes", None),
    ("GET", "/v1/children/{child}/devices", None),
    ("GET", "/v1/children/{child}/help-requests", None),
    ("GET", "/v1/children/{child}/question-reports", None),
    ("POST", "/v1/children/{child}/question-reports/" + LESSON + "/seen", None),
    ("DELETE", "/v1/children/{child}/devices/{device}", None),
    # Image d'une leçon (étape 27) : voir, valider, refuser, refaire.
    ("GET", "/v1/children/{child}/lessons/" + LESSON + "/image", None),
    ("GET", "/v1/children/{child}/lessons/" + LESSON + "/image/file", None),
    ("POST", "/v1/children/{child}/lessons/" + LESSON + "/image/approve", None),
    ("POST", "/v1/children/{child}/lessons/" + LESSON + "/image/reject", None),
    ("POST", "/v1/children/{child}/lessons/" + LESSON + "/image/redo", {}),
    ("GET", "/v1/children/{child}/lessons/" + LESSON + "/images/" + LESSON + "/file", None),
    ("POST", "/v1/children/{child}/lessons/" + LESSON + "/images/" + LESSON + "/approve", None),
    ("POST", "/v1/children/{child}/lessons/" + LESSON + "/images/" + LESSON + "/reject", None),
    ("POST", "/v1/children/{child}/lessons/" + LESSON + "/images/" + LESSON + "/redo", {}),
    ("POST", "/v1/children/{child}/lessons/" + LESSON + "/images/prepare", None),
    # Ressources des sites de confiance (étape 30) : voir, masquer, afficher, chercher.
    ("GET", "/v1/children/{child}/lessons/" + LESSON + "/resources", None),
    ("POST", "/v1/children/{child}/lessons/" + LESSON + "/resources/" + LESSON + "/hide", None),
    ("POST", "/v1/children/{child}/lessons/" + LESSON + "/resources/" + LESSON + "/show", None),
    ("POST", "/v1/children/{child}/lessons/" + LESSON + "/resources/prepare", None),
]
CHILD_SPECIFIC = [route for route in PARENT_ROUTES if "{child}" in route[1]]


@pytest.fixture
async def world(client: AsyncClient) -> dict[str, Any]:
    """Deux familles : Emma (famille A, un appareil lié) et Léo (famille B)."""
    a = await register(client, "a@example.fr")
    b = await register(client, "b@example.fr")
    emma = await add_child(client, a["access_token"], "Emma")
    leo = await add_child(client, b["access_token"], "Léo")
    device = await link_device(client, a["access_token"], emma["id"])
    return {"a": a["access_token"], "b": b["access_token"], "emma": emma, "leo": leo, "device": device}


def url(path: str, world: dict[str, Any]) -> str:
    return path.format(child=world["emma"]["id"], device=world["device"]["device_id"])


async def call(client: AsyncClient, method: str, path: str, body: Any, token: str | None) -> Any:
    headers = auth(token) if token else {}
    return await client.request(method, path, json=body, headers=headers)


@pytest.mark.parametrize("method, path, body", PARENT_ROUTES)
async def test_anonymous_is_rejected(
    client: AsyncClient, world: dict[str, Any], method: str, path: str, body: Any
) -> None:
    r = await call(client, method, url(path, world), body, None)
    assert r.status_code == 401


@pytest.mark.parametrize("method, path, body", PARENT_ROUTES)
async def test_child_device_cannot_use_parent_routes(
    client: AsyncClient, world: dict[str, Any], method: str, path: str, body: Any
) -> None:
    r = await call(client, method, url(path, world), body, world["device"]["token"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("method, path, body", CHILD_SPECIFIC)
async def test_other_family_sees_nothing(
    client: AsyncClient, world: dict[str, Any], method: str, path: str, body: Any
) -> None:
    r = await call(client, method, url(path, world), body, world["b"])
    assert r.status_code == 404
    # Rien n'a changé pour la famille A.
    children = (await client.get("/v1/children", headers=auth(world["a"]))).json()
    assert [(c["display_name"], c["grade"], c["devices"]) for c in children] == [("Emma", "CM1", 1)]


async def test_child_space_is_limited_to_its_own_child(client: AsyncClient, world: dict[str, Any]) -> None:
    device = world["device"]["token"]
    own = await client.get("/v1/me", params={"child_id": world["emma"]["id"]}, headers=auth(device))
    other = await client.get("/v1/me", params={"child_id": world["leo"]["id"]}, headers=auth(device))
    assert own.status_code == 200 and other.status_code == 404
    # Un parent ne voit pas l'espace d'un enfant d'une autre famille.
    r = await client.get("/v1/me", params={"child_id": world["emma"]["id"]}, headers=auth(world["b"]))
    assert r.status_code == 404


async def test_a_link_code_only_links_its_own_child(client: AsyncClient, world: dict[str, Any]) -> None:
    code = (
        await client.post(f"/v1/children/{world['leo']['id']}/link-codes", headers=auth(world["b"]))
    ).json()
    linked = (await client.post("/v1/link", json={"code": code["code"]})).json()
    assert linked["child"]["display_name"] == "Léo"
    assert (await client.get("/v1/me", headers=auth(linked["token"]))).json()["id"] == world["leo"]["id"]
