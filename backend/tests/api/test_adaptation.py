"""Critère de fin de l'étape 17 : deux échecs sur une notion déclenchent la remédiation ; des
réponses au hasard proposent une pause ; un enfant rapide se voit proposer des défis bonus."""

import uuid
from datetime import datetime
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import KnowledgeItem, SessionItem
from app.domain.simulated_pupil import Knows, respond
from app.services.learning import activity_of
from tests.api.helpers import auth, family_with_device, upload_lesson
from tests.api.test_sessions import knowledge_keys, now, play  # noqa: F401  (fixture)


async def answer(
    client: AsyncClient,
    db: AsyncSession,
    token: str,
    session_id: str,
    item: dict[str, Any],
    knows: Knows,
    ms: int,
) -> dict[str, Any]:
    row = await db.get(SessionItem, uuid.UUID(item["id"]))
    assert row is not None
    r = await client.post(
        f"/v1/sessions/{session_id}/attempts",
        json={
            "item_id": item["id"],
            "response": respond(activity_of(row, await knowledge_keys(db)), knows),
            "duration_ms": ms,
        },
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


async def start(client: AsyncClient) -> tuple[str, dict[str, Any], dict[str, Any]]:
    token = (await family_with_device(client))["device"]
    lesson = await upload_lesson(client, token)  # la Révolution française
    session = (await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))).json()
    return token, lesson, session


async def test_two_failures_trigger_a_remediation(
    client: AsyncClient,
    db: AsyncSession,
    now: list[datetime],  # noqa: F811
) -> None:
    token, _, session = await start(client)
    etats_generaux = await db.scalar(select(KnowledgeItem.id).where(KnowledgeItem.key == "k3"))
    knows: Knows = lambda key: key != "k3"  # noqa: E731
    queue, inserted_after, remediations = list(session["items"]), None, []
    while queue:
        item = queue.pop(0)
        feedback = await answer(client, db, token, session["id"], item, knows, 9000)
        if feedback["inserted_items"]:
            inserted_after, remediations = item, feedback["inserted_items"]
        queue = feedback["inserted_items"] + queue

    # Une seule remédiation, sur les États généraux, juste après le deuxième échec.
    assert inserted_after is not None and len(remediations) == 2
    assert {tuple(r["knowledge_ids"]) for r in remediations} == {(str(etats_generaux),)}
    assert {r["block"] for r in remediations} == {"remediation"}
    assert remediations[0]["intro"].startswith("📖 Rappel\u00a0: ") and remediations[1]["intro"] is None
    ordered = (await client.get(f"/v1/sessions/{session['id']}", headers=auth(token))).json()["items"]
    ids = [i["id"] for i in ordered]
    after = ids.index(inserted_after["id"])
    assert ids[after + 1 : after + 3] == [r["id"] for r in remediations]
    assert [i["position"] for i in ordered] == list(range(1, len(ordered) + 1))

    # La remédiation ne compte pas dans la note.
    replay = (await client.post(f"/v1/sessions/{session['id']}/replay", headers=auth(token))).json()
    await play(client, db, token, session["id"], replay["items"], lambda _: True)
    report = (await client.post(f"/v1/sessions/{session['id']}/complete", headers=auth(token))).json()
    main = [i for i in ordered if i["block"] in ("warmup", "core", "match", "speed")]
    scores = [i["attempt"]["score"] for i in main]
    assert report["score_on_10"] == round(20 * sum(scores) / len(scores)) / 2


async def test_random_answers_suggest_a_pause(
    client: AsyncClient,
    db: AsyncSession,
    now: list[datetime],  # noqa: F811
) -> None:
    token, _, session = await start(client)
    single = [i for i in session["items"] if i["type"] not in ("MATCH", "SPEED_CHALLENGE")]
    hints = [
        (await answer(client, db, token, session["id"], item, lambda _: False, 600))["engagement_hint"]
        for item in single[:4]
    ]
    assert hints[:2] == [None, None]
    assert hints[2] is not None and hints[2]["kind"] == "fast_guessing" and "pause" in hints[2]["message"]
    assert hints[3] is None  # on propose, on n'insiste pas


async def test_a_fast_child_gets_bonus_challenges(
    client: AsyncClient,
    db: AsyncSession,
    now: list[datetime],  # noqa: F811
) -> None:
    token, _, session = await start(client)
    url = f"/v1/sessions/{session['id']}"
    early = await client.post(f"{url}/extend", headers=auth(token))
    assert early.status_code == 409 and early.json()["error"]["code"] == "session_not_finished"

    await play(client, db, token, session["id"], session["items"], lambda _: True)
    replay = (await client.post(f"{url}/replay", headers=auth(token))).json()
    assert replay == {"items": [], "bonus_offer": True}
    bonus = (await client.post(f"{url}/extend", headers=auth(token))).json()["items"]
    assert 1 <= len(bonus) <= 3 and {i["block"] for i in bonus} == {"bonus"}
    assert all(i["difficulty"] >= 2 for i in bonus)
    again = (await client.post(f"{url}/extend", headers=auth(token))).json()["items"]
    assert [i["id"] for i in again] == [i["id"] for i in bonus]  # une seule fois

    await play(client, db, token, session["id"], bonus, lambda _: False)  # même ratés…
    report = (await client.post(f"{url}/complete", headers=auth(token))).json()
    assert report["score_on_10"] == 10  # …les défis bonus ne coûtent rien à la note


async def test_no_bonus_for_a_slow_or_struggling_child(
    client: AsyncClient,
    db: AsyncSession,
    now: list[datetime],  # noqa: F811
) -> None:
    token, _, session = await start(client)
    for item in session["items"]:
        await answer(client, db, token, session["id"], item, lambda _: True, 120_000)
    replay = (await client.post(f"/v1/sessions/{session['id']}/replay", headers=auth(token))).json()
    assert replay["bonus_offer"] is False


async def test_remediation_goes_back_to_a_prerequisite_first(
    client: AsyncClient,
    db: AsyncSession,
    now: list[datetime],  # noqa: F811
) -> None:
    """§5.72 : la notion ratée est un exemple d'une notion pas encore sue : celle-ci d'abord."""
    family = await family_with_device(client)
    token = family["device"]
    lesson = await upload_lesson(client, token)
    session = (await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))).json()
    rows = {
        row.key: row
        for row in await db.scalars(select(KnowledgeItem).where(KnowledgeItem.key.in_(["k1", "k3"])))
    }
    rows["k3"].relations = [*rows["k3"].relations, {"type": "example_of", "target": "k1"}]
    await db.commit()
    knows: Knows = lambda key: key != "k3"  # noqa: E731
    queue, remediations = list(session["items"]), []
    while queue:
        item = queue.pop(0)
        feedback = await answer(client, db, token, session["id"], item, knows, 9000)
        if feedback["inserted_items"]:
            remediations = feedback["inserted_items"]
        queue = feedback["inserted_items"] + queue

    assert len(remediations) == 3 and {r["block"] for r in remediations} == {"remediation"}
    first, second, third = remediations
    assert first["knowledge_ids"] == [str(rows["k1"].id)]
    assert first["intro"].startswith("📖 On revient d'abord sur")
    assert second["knowledge_ids"] == third["knowledge_ids"] == [str(rows["k3"].id)]
    assert second["intro"].startswith("📖 Rappel : ") and third["intro"] is None
    url = f"/v1/children/{family['child']['id']}/sessions/{session['id']}"
    detail = (await client.get(url, headers=auth(family["parent"]))).json()
    reasons = [a["reason"] for a in detail["activities"] if a["block"] == "remediation"]
    assert reasons[0].startswith("Échecs répétés sur « États généraux » : on revient d'abord sur « 1789 »")
    assert reasons[1].startswith("2 échecs sur cette notion")
    assert [d["rule"] for d in detail["decisions"]].count("prerequisite") == 1
