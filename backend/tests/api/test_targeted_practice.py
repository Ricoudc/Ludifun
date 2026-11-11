"""§5.74 : une erreur qui revient sur une notion (3 séances) donne, après la séance, un exercice
neuf qui la vise ; contrôlé par le code, tracé dans le suivi, jamais deux fois pour la même erreur."""

from datetime import datetime
from typing import Any

from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.ports import AIError
from app.ai.providers.fake import FakeProvider
from app.db.models import AiRun, AttemptEvidence, KnowledgeItem, KnowledgeMaterial, RevisionSession
from tests.api.helpers import auth, family_with_device, upload_lesson
from tests.api.test_sessions import now, play  # noqa: F401  (fixture)


async def targeted_questions(db: AsyncSession, key: str) -> list[dict[str, Any]]:
    db.expire_all()
    material = await db.scalar(
        select(KnowledgeMaterial.material)
        .join(KnowledgeItem, KnowledgeItem.id == KnowledgeMaterial.knowledge_id)
        .where(KnowledgeItem.key == key)
    )
    assert material is not None
    return [q for q in material["questions"] if q.get("target_error")]


async def runs(db: AsyncSession) -> int:
    return await db.scalar(select(func.count()).select_from(AiRun).where(AiRun.stage == "targeted")) or 0


async def three_sessions_with_the_same_error(
    client: AsyncClient, db: AsyncSession
) -> tuple[dict[str, Any], dict[str, Any], str]:
    family = await family_with_device(client)
    token = family["device"]
    lesson = await upload_lesson(client, token)
    k3 = await db.scalar(select(KnowledgeItem.id).where(KnowledgeItem.key == "k3"))
    for session_number in range(3):
        session = (
            await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))
        ).json()
        await play(client, db, token, session["id"], session["items"], lambda key: key != "k3")
        # La même erreur à chaque séance (le type précis dépend de la réponse de l'élève simulé).
        await db.execute(
            update(AttemptEvidence)
            .where(AttemptEvidence.knowledge_id == k3, AttemptEvidence.error_type.is_not(None))
            .values(error_type="confusion")
        )
        await db.commit()
        r = await client.post(f"/v1/sessions/{session['id']}/complete", headers=auth(token))
        assert r.status_code == 200, r.text
        if session_number < 2:  # pas encore récurrente : aucun appel à l'IA
            assert await runs(db) == 0 and await targeted_questions(db, "k3") == []
    return family, lesson, token


async def test_a_recurring_error_gets_a_new_exercise(
    client: AsyncClient,
    db: AsyncSession,
    now: list[datetime],  # noqa: F811
) -> None:
    family, lesson, token = await three_sessions_with_the_same_error(client, db)
    questions = await targeted_questions(db, "k3")
    assert len(questions) == 1 and questions[0]["target_error"] == "confusion"
    assert questions[0]["misconceptions"][0] == "confusion" and questions[0]["target_why"]
    assert await runs(db) == 1

    # Une fois l'exercice prêt, la même erreur ne relance plus l'IA.
    session = (await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))).json()
    await play(client, db, token, session["id"], session["items"], lambda key: key != "k3")
    await client.post(f"/v1/sessions/{session['id']}/complete", headers=auth(token))
    assert await runs(db) == 1 and len(await targeted_questions(db, "k3")) == 1

    # Le parent le voit dans la relecture de la leçon, avec l'erreur visée et le piège.
    url = f"/v1/children/{family['child']['id']}/lessons/{lesson['id']}/content"
    content = (await client.get(url, headers=auth(family["parent"]))).json()
    blocks = [b for n in content["notions"] for b in n["blocks"] if b["title"].startswith("🎯")]
    assert len(blocks) == 1 and "Erreur visée : confond avec une autre notion" in blocks[0]["lines"][0]


async def test_an_ai_failure_changes_nothing_for_the_child(
    client: AsyncClient,
    db: AsyncSession,
    fake_llm: FakeProvider,
    now: list[datetime],  # noqa: F811
) -> None:
    """L'IA en panne : le bilan arrive quand même, aucune question n'est ajoutée, la panne est
    tracée dans le suivi."""
    fake_llm.overrides["targeted"] = AIError("API 529 : overloaded")
    await three_sessions_with_the_same_error(client, db)
    assert await targeted_questions(db, "k3") == []
    status = await db.scalar(select(AiRun.status).where(AiRun.stage == "targeted"))
    assert status == "error"



async def test_abandoned_sessions_do_not_make_an_error_recurring(
    client: AsyncClient,
    db: AsyncSession,
    now: list[datetime],  # noqa: F811
) -> None:
    """Deux séances terminées + une abandonnée ne font pas trois séances récurrentes."""
    family = await family_with_device(client)
    token = family["device"]
    lesson = await upload_lesson(client, token)
    k3 = await db.scalar(select(KnowledgeItem.id).where(KnowledgeItem.key == "k3"))

    for session_number in range(3):
        session = (
            await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))
        ).json()
        await play(client, db, token, session["id"], session["items"], lambda key: key != "k3")
        await db.execute(
            update(AttemptEvidence)
            .where(AttemptEvidence.knowledge_id == k3, AttemptEvidence.error_type.is_not(None))
            .values(error_type="confusion")
        )
        await db.commit()
        if session_number < 2:
            completed = await client.post(f"/v1/sessions/{session['id']}/complete", headers=auth(token))
            assert completed.status_code == 200, completed.text
        else:
            await db.execute(
                update(RevisionSession).where(RevisionSession.id == session["id"]).values(status="abandoned")
            )
            await db.commit()

    # Une quatrième séance terminée déclenche le calcul : seules deux séances contiennent
    # une erreur de confusion terminée, la troisième occurrence est dans une séance abandonnée.
    session = (await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))).json()
    await play(client, db, token, session["id"], session["items"], lambda _: True)
    completed = await client.post(f"/v1/sessions/{session['id']}/complete", headers=auth(token))
    assert completed.status_code == 200, completed.text
    assert await targeted_questions(db, "k3") == []
    assert await runs(db) == 0

    board = (await client.get(
        f"/v1/children/{family['child']['id']}/dashboard", headers=auth(family["parent"])
    )).json()
    assert board["recurring_errors"] == []
