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
