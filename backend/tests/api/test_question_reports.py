"""🚩 L'enfant signale une question bizarre ; le parent la voit, avec la réponse de l'enfant et
celle retenue par Ludifun, puis la marque comme vue. La note et la progression ne changent pas."""

from datetime import datetime
from typing import Any

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.fake import FakeProvider
from app.db.models import KnowledgeMastery
from tests.api.helpers import auth, family_with_device
from tests.api.test_help_and_open_questions import fractions, start
from tests.api.test_sessions import now, play  # noqa: F401  (fixture)


def report_url(session: dict[str, Any], item: dict[str, Any]) -> str:
    return f"/v1/sessions/{session['id']}/items/{item['id']}/report"


async def test_the_child_reports_a_question_and_the_parent_sees_it(
    client: AsyncClient,
    db: AsyncSession,
    fake_llm: FakeProvider,
    now: list[datetime],  # noqa: F811
) -> None:
    family, lesson = await fractions(client, fake_llm)
    token, parent = family["device"], auth(family["parent"])
    child_id = family["child"]["id"]
    url = f"/v1/children/{child_id}/question-reports"
    assert (await client.get(url, headers=parent)).json() == {"reports": [], "next_before": None}

    session = await start(client, token, lesson["id"])
    first, second = session["items"][:2]
    # Avant de répondre : « Je ne comprends pas la question ».
    r = await client.post(report_url(session, first), json={"reason": "unclear"}, headers=auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["reason"] == "unclear"
    # Après une réponse fausse : « Ma réponse était juste ».
    await play(client, db, token, session["id"], [second], lambda _: False)
    r = await client.post(report_url(session, second), json={"reason": "right_answer"}, headers=auth(token))
    assert r.status_code == 200
    masteries = await db.scalar(select(func.count(KnowledgeMastery.knowledge_id)))

    # Un seul signalement par question : un nouvel appui change la raison.
    r = await client.post(report_url(session, first), json={"reason": "wrong_question"}, headers=auth(token))
    assert r.status_code == 200
    bad = await client.post(report_url(session, first), json={"reason": "autre"}, headers=auth(token))
    assert bad.status_code == 422
    free_text = await client.post(
        report_url(session, first), json={"reason": "unclear", "text": "Emma"}, headers=auth(token)
    )
    assert free_text.status_code == 422  # rien d'écrit par l'enfant

    reports = (await client.get(url, headers=parent)).json()["reports"]
    assert [r["reason"] for r in reports] == ["wrong_question", "right_answer"]
    unanswered, answered = reports
    assert unanswered["outcome"] == "unanswered" and unanswered["given"] is None
    assert unanswered["reason_label"] == "Il y a une erreur dans la question"
    assert unanswered["question"] and unanswered["expected"] and unanswered["lesson_title"] == "Les fractions"
    assert answered["outcome"] in {"wrong", "partial"} and answered["given"] and answered["expected"]
    assert not any(r["seen"] for r in reports)
    board = (await client.get(f"/v1/children/{child_id}/dashboard", headers=parent)).json()
    assert board["reports_to_see"] == 2
    # « En bref » le dit aussi, et conseille de commencer par là.
    assert "🚩 2 questions signalées à regarder." in board["summary"]
    assert board["summary"][0].startswith("📅 Révisé 1 jour sur 7 : ")
    assert board["summary"][-1].startswith("👉 Regardez d'abord les questions signalées")

    # Le parent l'a regardée : elle reste dans la liste, marquée vue.
    seen = await client.post(f"{url}/{answered['id']}/seen", headers=parent)
    assert seen.status_code == 204
    assert (await client.post(f"{url}/{answered['id']}/seen", headers=parent)).status_code == 204
    reports = (await client.get(url, headers=parent)).json()["reports"]
    assert [r["seen"] for r in reports] == [False, True]
    board = (await client.get(f"/v1/children/{child_id}/dashboard", headers=parent)).json()
    assert board["reports_to_see"] == 1

    # La progression n'a pas bougé ; l'export contient les signalements.
    assert await db.scalar(select(func.count(KnowledgeMastery.knowledge_id))) == masteries
    export = (await client.get(f"/v1/children/{child_id}/export", headers=parent)).json()
    exported = [r for s in export["sessions"] for r in s["question_reports"]]
    assert sorted(r["reason"] for r in exported) == ["right_answer", "wrong_question"]

    # Un autre parent, un autre enfant : rien.
    other = await family_with_device(client, "autre@example.fr")
    assert (await client.get(url, headers=auth(other["parent"]))).status_code == 404
    r = await client.post(f"{url}/{answered['id']}/seen", headers=auth(other["parent"]))
    assert r.status_code == 404
    r = await client.post(
        report_url(session, first), json={"reason": "unclear"}, headers=auth(other["device"])
    )
    assert r.status_code == 404
    other_url = f"/v1/children/{other['child']['id']}/question-reports"
    r = await client.post(f"{other_url}/{answered['id']}/seen", headers=auth(other["parent"]))
    assert r.status_code == 404
