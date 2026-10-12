"""Raison de chaque décision du moteur (CDC §126, §138) : visible par le parent, séance par séance."""

from datetime import datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.rules import ENGINE_VERSION
from tests.api.helpers import auth, family_with_device, register, upload_lesson
from tests.api.test_adaptation import answer
from tests.api.test_sessions import now, play  # noqa: F401  (fixture)


async def test_every_activity_and_decision_has_its_reason(
    client: AsyncClient,
    db: AsyncSession,
    now: list[datetime],  # noqa: F811
) -> None:
    family = await family_with_device(client)
    token, parent = family["device"], family["parent"]
    lesson = await upload_lesson(client, token)
    session = (await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))).json()
    url = f"/v1/children/{family['child']['id']}/sessions/{session['id']}"

    # Trois notions ratées, vite : remédiation (deux échecs) et pause proposée (réponses au hasard).
    queue = list(session["items"])
    while queue:
        item = queue.pop(0)
        feedback = await answer(
            client, db, token, session["id"], item, lambda key: key not in ("k1", "k2", "k3"), 700
        )
        queue = feedback["inserted_items"] + queue

    detail = (await client.get(url, headers=auth(parent))).json()
    assert detail["engine_version"] == ENGINE_VERSION
    activities = detail["activities"]
    assert activities and all(a["reason"] for a in activities)
    assert activities[0]["reason"].startswith("Première séance : notion d'importance")
    remediation = [a for a in activities if a["block"] == "remediation"]
    assert remediation and remediation[0]["reason"].startswith("2 échecs sur cette notion")
    assert len(remediation[0]["notions"]) == 1
    assert {a["result"] for a in activities} <= {"correct", "partial", "incorrect"}
    rules = [d["rule"] for d in detail["decisions"]]
    assert "remediation" in rules and "pause_fast_guessing" in rules
    pause = next(d for d in detail["decisions"] if d["rule"] == "pause_fast_guessing")
    assert "réponses fausses très rapides" in pause["text"]

    # Séparation parent / enfant : ni l'enfant ni un autre parent n'y ont accès.
    assert (await client.get(url, headers=auth(token))).status_code in (401, 403)
    other = await register(client, "autre@example.fr")
    assert (await client.get(url, headers=auth(other["access_token"]))).status_code == 404


async def test_bonus_decision(
    client: AsyncClient,
    db: AsyncSession,
    now: list[datetime],  # noqa: F811
) -> None:
    family = await family_with_device(client)
    token = family["device"]
    lesson = await upload_lesson(client, token)
    session = (await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))).json()
    await play(client, db, token, session["id"], session["items"], lambda _: True)
    await client.post(f"/v1/sessions/{session['id']}/replay", headers=auth(token))
    await client.post(f"/v1/sessions/{session['id']}/extend", headers=auth(token))
    detail = (
        await client.get(
            f"/v1/children/{family['child']['id']}/sessions/{session['id']}", headers=auth(family["parent"])
        )
    ).json()
    (bonus,) = [d for d in detail["decisions"] if d["rule"] == "bonus"]
    assert bonus["text"].startswith("Séance réussie à 100 % et rapide")
    assert all(a["reason"] == bonus["text"] for a in detail["activities"] if a["block"] == "bonus")


async def test_parent_sees_facts_levels_and_independence(
    client: AsyncClient,
    db: AsyncSession,
    now: list[datetime],  # noqa: F811
) -> None:
    family = await family_with_device(client)
    token = family["device"]
    lesson = await upload_lesson(client, token)
    session = (await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))).json()
    await play(client, db, token, session["id"], session["items"], lambda key: key != "k3")
    await client.post(f"/v1/sessions/{session['id']}/complete", headers=auth(token))

    skills = (
        await client.get(f"/v1/children/{family['child']['id']}/skills", headers=auth(family["parent"]))
    ).json()
    notions = {n["label"]: n for n in skills["lessons"][0]["notions"]}
    failed = notions["États généraux"]
    assert failed["facts"].startswith("Sur les ") and "ratée" in failed["facts"]
    assert [r["name"] for r in failed["level_rates"]] == [
        "reconnaître",
        "se rappeler",
        "appliquer",
        "expliquer",
        "transférer",
    ]
    assert failed["level_rates"][0]["rate"] is not None and failed["level_rates"][4]["rate"] is None
    known = next(n for label, n in notions.items() if label != "États généraux" and n["facts"])
    assert known["independence"] == 1.0 and "réussie" in known["facts"]
    assert known["explanation"]  # l'interprétation reste à part


async def test_why_this_notion(client: AsyncClient) -> None:
    """§116 : chaque notion montre la phrase de la leçon d'où elle vient, et sa page."""
    family = await family_with_device(client)
    lesson = await upload_lesson(client, family["device"])
    assert lesson["knowledge"]
    for notion in lesson["knowledge"]:
        assert notion["source_excerpt"] and notion["source_page"] == 1
