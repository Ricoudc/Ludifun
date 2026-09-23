from typing import Any

from httpx import AsyncClient

PASSWORD = "un mot de passe solide"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def register(client: AsyncClient, email: str = "parent@example.fr") -> dict[str, Any]:
    r = await client.post(
        "/v1/auth/register", json={"email": email, "password": PASSWORD, "accepted_privacy_policy": True}
    )
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    return body


async def add_child(
    client: AsyncClient, parent_token: str, name: str = "Emma", grade: str = "CM1"
) -> dict[str, Any]:
    r = await client.post(
        "/v1/children",
        json={"display_name": name, "grade": grade, "parental_consent": True},
        headers=auth(parent_token),
    )
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    return body


async def link_device(
    client: AsyncClient, parent_token: str, child_id: str, name: str = "Tablette"
) -> dict[str, Any]:
    code = (await client.post(f"/v1/children/{child_id}/link-codes", headers=auth(parent_token))).json()
    r = await client.post("/v1/link", json={"code": code["code"], "device_name": name})
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    return body


PHOTO = b"\xff\xd8\xff\xe0" + b"photo de lecon" * 10


async def family_with_device(client: AsyncClient, email: str = "parent@example.fr") -> dict[str, Any]:
    """Un parent, Emma, et la tablette d'Emma liée."""
    parent = (await register(client, email))["access_token"]
    child = await add_child(client, parent)
    device = await link_device(client, parent, child["id"])
    return {"parent": parent, "child": child, "device": device["token"]}


async def upload_lesson(client: AsyncClient, token: str, pages: int = 1, **params: str) -> dict[str, Any]:
    files = [("pages", (f"page{i}.jpg", PHOTO, "image/jpeg")) for i in range(pages)]
    r = await client.post("/v1/lessons", files=files, headers=auth(token), params=params)
    assert r.status_code == 202, r.text
    # L'analyse (IA factice) s'exécute en tâche de fond avant la fin de la requête de test.
    lesson = await client.get(f"/v1/lessons/{r.json()['id']}", headers=auth(token), params=params)
    body: dict[str, Any] = lesson.json()
    return body
