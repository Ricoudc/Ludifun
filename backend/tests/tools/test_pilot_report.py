"""Rapport des tests en famille : indicateurs agrégés, sans contenu de leçon ni prénom."""

from datetime import datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.simulated_pupil import Knows
from app.tools.pilot_report import collect, render
from tests.api.helpers import add_child, auth, family_with_device, upload_lesson
from tests.api.test_sessions import now, play  # noqa: F401  (fixture)


async def test_report_on_a_small_pilot(
    client: AsyncClient,
    db: AsyncSession,
    now: list[datetime],  # noqa: F811
) -> None:
    family = await family_with_device(client)
    await add_child(client, family["parent"], "Hugo", "CE2")  # inscrit, jamais actif
    token = family["device"]
    lesson = await upload_lesson(client, token)
    knows: Knows = lambda key: key != "k3"  # noqa: E731

    # Première séance : une aide demandée, terminée.
    first = (await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))).json()
    item = first["items"][0]
    r = await client.post(f"/v1/sessions/{first['id']}/items/{item['id']}/help", headers=auth(token))
    assert r.status_code == 200, r.text
    await play(client, db, token, first["id"], first["items"], knows)
    await client.post(f"/v1/sessions/{first['id']}/complete", headers=auth(token))
    await client.post("/v1/feedback", json={"rating": 5, "screen": "report"}, headers=auth(token))
    await client.post(
        "/v1/feedback",
        json={"rating": 4, "message": "Très utile avant le contrôle."},
        headers=auth(family["parent"]),
    )

    # Deuxième séance, deux jours plus tard : sans aide.
    now[0] += timedelta(days=2)
    second = (await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))).json()
    await play(client, db, token, second["id"], second["items"], lambda _: True)
    await client.post(f"/v1/sessions/{second['id']}/complete", headers=auth(token))

    report = await collect(db, (now[0] - timedelta(days=3)).date(), now[0].date())
    assert (report.families, len(report.children)) == (1, 1)
    assert (report.sessions, report.completed, report.abandoned, report.completed_without_help) == (
        2,
        2,
        0,
        1,
    )
    assert report.help_requests == 1 and report.answers >= len(first["items"])
    assert report.remediations == 1  # deux échecs sur les États généraux
    assert report.errors and report.lessons == 1 and report.lessons_ready == 1
    assert report.lessons_by_source == {"photo": 1}
    assert report.cost_per_lesson and report.notions_practised > 0
    assert (report.child_ratings, report.parent_ratings) == ([5], [4])

    text = render(report)
    assert "Enfant 1 (CM1)" in text and "« Très utile avant le contrôle. »" in text
    assert "Emma" not in text and "Hugo" not in text  # ni prénom…
    assert all(k["label"] not in text for k in lesson["knowledge"])  # …ni contenu de leçon
    assert "| Séances terminées | 100 % | ≥ 80 % | ✅ |" in text

    # Une période sans activité : des tirets, pas d'erreur.
    empty = render(await collect(db, now[0].date() + timedelta(days=1), now[0].date() + timedelta(days=2)))
    assert "0 famille(s)" in empty and "Aucun message." in empty
