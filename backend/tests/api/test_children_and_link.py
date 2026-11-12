from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.children import GLOBAL_LINK_FAILURES
from app.db.models import Child, Device, LinkCode, Parent
from tests.api.helpers import add_child, auth, link_device, register


async def test_children_crud(client: AsyncClient) -> None:
    token = (await register(client))["access_token"]
    emma = await add_child(client, token, "Emma", "CM1")
    await add_child(client, token, "Hugo", "CE1")
    children = (await client.get("/v1/children", headers=auth(token))).json()
    assert [(c["display_name"], c["grade"], c["devices"]) for c in children] == [
        ("Emma", "CM1", 0),
        ("Hugo", "CE1", 0),
    ]

    r = await client.patch(
        f"/v1/children/{emma['id']}", json={"grade": "CM2", "avatar": "🦊"}, headers=auth(token)
    )
    assert (r.json()["grade"], r.json()["avatar"]) == ("CM2", "🦊")
    assert (
        await client.patch(f"/v1/children/{emma['id']}", json={"grade": None}, headers=auth(token))
    ).status_code == 422

    assert (await client.delete(f"/v1/children/{emma['id']}", headers=auth(token))).status_code == 204
    assert [c["display_name"] for c in (await client.get("/v1/children", headers=auth(token))).json()] == [
        "Hugo"
    ]


async def test_child_creation_requires_consent_and_valid_grade(client: AsyncClient) -> None:
    token = (await register(client))["access_token"]
    for body in (
        {"display_name": "Emma", "grade": "CM1", "parental_consent": False},
        {"display_name": "Emma", "grade": "CM1"},
        {"display_name": "Emma", "grade": "Terminale", "parental_consent": True},
        {"display_name": "  ", "grade": "CM1", "parental_consent": True},
    ):
        assert (await client.post("/v1/children", json=body, headers=auth(token))).status_code == 422


async def test_link_with_code(client: AsyncClient) -> None:
    token = (await register(client))["access_token"]
    emma = await add_child(client, token)
    code = (await client.post(f"/v1/children/{emma['id']}/link-codes", headers=auth(token))).json()
    assert len(code["code"]) == 6 and code["code"].isdigit()
    assert code["qr"].startswith("ludifun://lier/")

    linked = await client.post("/v1/link", json={"code": code["code"], "device_name": "Tablette"})
    assert linked.status_code == 201
    body = linked.json()
    assert body["child"] == {"id": emma["id"], "display_name": "Emma", "grade": "CM1", "avatar": None}
    assert body["token"].startswith("ldf_d_")

    me = await client.get("/v1/me", headers=auth(body["token"]))
    assert me.json()["display_name"] == "Emma"
    devices = (await client.get(f"/v1/children/{emma['id']}/devices", headers=auth(token))).json()
    assert [d["name"] for d in devices] == ["Tablette"]

    # Usage unique.
    again = await client.post("/v1/link", json={"code": code["code"]})
    assert again.status_code == 400 and again.json()["error"]["code"] == "invalid_link_code"


async def test_link_with_qr_code(client: AsyncClient) -> None:
    token = (await register(client))["access_token"]
    emma = await add_child(client, token)
    code = (await client.post(f"/v1/children/{emma['id']}/link-codes", headers=auth(token))).json()
    r = await client.post("/v1/link", json={"qr_token": code["qr"]})
    assert r.status_code == 201 and r.json()["child"]["id"] == emma["id"]


async def test_link_input_validation(client: AsyncClient) -> None:
    for body in ({}, {"code": "12345"}, {"code": "abcdef"}, {"code": "123456", "qr_token": "x" * 20}):
        assert (await client.post("/v1/link", json=body)).status_code == 422


async def test_expired_and_replaced_codes(client: AsyncClient, db: AsyncSession) -> None:
    token = (await register(client))["access_token"]
    emma = await add_child(client, token)
    first = (await client.post(f"/v1/children/{emma['id']}/link-codes", headers=auth(token))).json()
    second = (await client.post(f"/v1/children/{emma['id']}/link-codes", headers=auth(token))).json()
    # Un nouveau code annule le précédent (sauf tirage identique, une chance sur un million).
    if first["code"] != second["code"]:
        assert (await client.post("/v1/link", json={"code": first["code"]})).status_code == 400

    await db.execute(update(LinkCode).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    await db.commit()
    assert (await client.post("/v1/link", json={"code": second["code"]})).status_code == 400


async def test_wrong_codes_are_rate_limited(client: AsyncClient) -> None:
    codes = [(await client.post("/v1/link", json={"code": f"{i:06d}"})).status_code for i in range(11)]
    assert codes == [400] * 10 + [429]


async def test_revoked_device_loses_access(client: AsyncClient) -> None:
    token = (await register(client))["access_token"]
    emma = await add_child(client, token)
    device = await link_device(client, token, emma["id"])
    r = await client.delete(f"/v1/children/{emma['id']}/devices/{device['device_id']}", headers=auth(token))
    assert r.status_code == 204
    me = await client.get("/v1/me", headers=auth(device["token"]))
    assert me.status_code == 401 and me.json()["error"]["code"] == "invalid_token"
    assert (await client.get(f"/v1/children/{emma['id']}/devices", headers=auth(token))).json() == []
    again = await client.delete(
        f"/v1/children/{emma['id']}/devices/{device['device_id']}", headers=auth(token)
    )
    assert again.status_code == 404


async def test_device_unlinks_itself(client: AsyncClient) -> None:
    """« Ce n'est pas moi » : l'appareil rend son jeton ; un parent ne peut pas appeler cette route."""
    token = (await register(client))["access_token"]
    emma = await add_child(client, token)
    device = await link_device(client, token, emma["id"])
    parent_call = await client.delete("/v1/me/device", headers=auth(token))
    assert parent_call.status_code == 403
    assert (await client.delete("/v1/me/device", headers=auth(device["token"]))).status_code == 204
    assert (await client.get("/v1/me", headers=auth(device["token"]))).status_code == 401
    assert (await client.get(f"/v1/children/{emma['id']}/devices", headers=auth(token))).json() == []


async def test_parent_reads_child_space_with_child_id(client: AsyncClient) -> None:
    token = (await register(client))["access_token"]
    emma = await add_child(client, token)
    assert (await client.get("/v1/me", headers=auth(token))).json()["error"]["code"] == "child_id_required"
    r = await client.get("/v1/me", params={"child_id": emma["id"]}, headers=auth(token))
    assert r.status_code == 200 and r.json()["display_name"] == "Emma"


async def test_deleting_a_child_unlinks_its_devices(client: AsyncClient, db: AsyncSession) -> None:
    token = (await register(client))["access_token"]
    emma = await add_child(client, token)
    device = await link_device(client, token, emma["id"])
    await client.delete(f"/v1/children/{emma['id']}", headers=auth(token))
    assert (await client.get("/v1/me", headers=auth(device["token"]))).status_code == 401
    assert await db.scalar(select(func.count()).select_from(Device)) == 0


async def test_deleting_the_parent_erases_the_family(client: AsyncClient, db: AsyncSession) -> None:
    token = (await register(client))["access_token"]
    for name in ("Emma", "Hugo"):
        child = await add_child(client, token, name)
        await link_device(client, token, child["id"])
    assert (await client.delete("/v1/parent", headers=auth(token))).status_code == 204
    for model in (Parent, Child, Device):
        assert await db.scalar(select(func.count()).select_from(model)) == 0
    assert (await client.get("/v1/parent", headers=auth(token))).status_code == 401


async def test_global_link_failure_ceiling(client: AsyncClient, app: FastAPI) -> None:
    """Une attaque répartie sur de nombreuses IP finit bloquée par le plafond global."""
    token = (await register(client))["access_token"]
    emma = await add_child(client, token)
    code = (await client.post(f"/v1/children/{emma['id']}/link-codes", headers=auth(token))).json()
    key, limit, window = GLOBAL_LINK_FAILURES
    for _ in range(limit):
        app.state.rate_limiter.hit(key, limit, window)
    blocked = await client.post("/v1/link", json={"code": code["code"]})
    assert blocked.status_code == 429  # même le bon code, le temps que l'attaque cesse
    app.state.rate_limiter.reset(key)
    assert (await client.post("/v1/link", json={"code": code["code"]})).status_code == 201
