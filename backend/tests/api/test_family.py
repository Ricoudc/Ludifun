"""Un second parent dans la famille (§5.92) : invité par un code, il voit les mêmes enfants ; il
peut partir ou être retiré ; son départ ne touche ni la famille ni les enfants."""

from httpx import AsyncClient

from tests.api.helpers import add_child, auth, link_device, register, upload_lesson


async def _invite(client: AsyncClient, owner: str) -> str:
    r = await client.post("/v1/parent/invites", headers=auth(owner))
    assert r.status_code == 201, r.text
    code: str = r.json()["code"]
    assert len(code) == 9 and code[4] == "-"
    return code


async def test_a_second_parent_joins_and_sees_the_same_children(client: AsyncClient) -> None:
    owner = (await register(client, "maman@example.fr"))["access_token"]
    emma = await add_child(client, owner, "Emma")
    device = await link_device(client, owner, emma["id"])
    lesson = await upload_lesson(client, device["token"])
    other = (await register(client, "papa@example.fr"))["access_token"]
    assert (await client.get("/v1/children", headers=auth(other))).json() == []

    code = await _invite(client, owner)
    typed = code.lower().replace("-", " ")  # tapé à la main : minuscules, espace au lieu du tiret
    joined = await client.post("/v1/parent/join", json={"code": typed}, headers=auth(other))
    assert joined.status_code == 200, joined.text
    roles = {(m["email"], m["role"], m["me"]) for m in joined.json()["members"]}
    assert roles == {("maman@example.fr", "owner", False), ("papa@example.fr", "member", True)}
    assert joined.json()["can_invite"] is False

    children = (await client.get("/v1/children", headers=auth(other))).json()
    assert [c["display_name"] for c in children] == ["Emma"]
    content = await client.get(
        f"/v1/children/{emma['id']}/lessons/{lesson['id']}/content", headers=auth(other)
    )
    assert content.status_code == 200
    # Il peut ajouter un enfant : il arrive dans la même famille.
    leo = await add_child(client, other, "Léo")
    names = sorted(c["display_name"] for c in (await client.get("/v1/children", headers=auth(owner))).json())
    assert names == ["Emma", "Léo"] and leo["id"]
    # Le code ne sert qu'une fois, et la famille est complète.
    third = (await register(client, "autre@example.fr"))["access_token"]
    again = await client.post("/v1/parent/join", json={"code": code}, headers=auth(third))
    assert again.status_code == 404 and again.json()["error"]["code"] == "invite_invalid"
    full = await client.post("/v1/parent/invites", headers=auth(owner))
    assert full.status_code == 409 and full.json()["error"]["code"] == "family_full"
    member = await client.post("/v1/parent/invites", headers=auth(other))
    assert member.status_code == 403


async def test_joining_needs_an_account_without_children(client: AsyncClient) -> None:
    owner = (await register(client, "a@example.fr"))["access_token"]
    await add_child(client, owner, "Emma")
    other = (await register(client, "b@example.fr"))["access_token"]
    await add_child(client, other, "Léo")
    code = await _invite(client, owner)
    r = await client.post("/v1/parent/join", json={"code": code}, headers=auth(other))
    assert r.status_code == 409 and r.json()["error"]["code"] == "own_family_not_empty"
    # Rien n'a bougé : chacun garde son enfant, le code reste valable.
    assert [c["display_name"] for c in (await client.get("/v1/children", headers=auth(other))).json()] == [
        "Léo"
    ]
    unknown = await client.post("/v1/parent/join", json={"code": "ZZZZ-ZZZZ"}, headers=auth(other))
    assert unknown.status_code == 404


async def test_the_second_parent_leaves_or_is_removed_and_the_family_stays(client: AsyncClient) -> None:
    owner = (await register(client, "a@example.fr"))["access_token"]
    await add_child(client, owner, "Emma")
    other = (await register(client, "b@example.fr"))["access_token"]
    await client.post("/v1/parent/join", json={"code": await _invite(client, owner)}, headers=auth(other))
    members = (await client.get("/v1/parent/members", headers=auth(owner))).json()["members"]
    member_id = next(m["parent_id"] for m in members if m["role"] == "member")
    owner_id = next(m["parent_id"] for m in members if m["role"] == "owner")

    # Le second parent ne peut pas retirer le propriétaire.
    r = await client.delete(f"/v1/parent/members/{owner_id}", headers=auth(other))
    assert r.status_code == 404
    # Le propriétaire le retire : il ne voit plus les enfants, retrouve une famille à lui.
    r = await client.delete(f"/v1/parent/members/{member_id}", headers=auth(owner))
    assert r.status_code == 204
    assert (await client.get("/v1/children", headers=auth(other))).json() == []
    own = (await client.get("/v1/parent/members", headers=auth(other))).json()
    assert own["can_invite"] is True and [m["role"] for m in own["members"]] == ["owner"]
    await add_child(client, other, "Léo")  # sa propre famille marche
    assert [c["display_name"] for c in (await client.get("/v1/children", headers=auth(owner))).json()] == [
        "Emma"
    ]


async def test_deleting_the_second_parents_account_keeps_the_family(client: AsyncClient) -> None:
    owner = (await register(client, "a@example.fr"))["access_token"]
    await add_child(client, owner, "Emma")
    other = (await register(client, "b@example.fr"))["access_token"]
    await client.post("/v1/parent/join", json={"code": await _invite(client, owner)}, headers=auth(other))
    deleted = await client.delete("/v1/parent", headers=auth(other))
    assert deleted.status_code == 204, deleted.text
    children = (await client.get("/v1/children", headers=auth(owner))).json()
    assert [c["display_name"] for c in children] == ["Emma"]
    members = (await client.get("/v1/parent/members", headers=auth(owner))).json()
    assert [m["role"] for m in members["members"]] == ["owner"] and members["can_invite"] is True
