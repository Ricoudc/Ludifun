"""Étape 25 : le parent relit les questions d'une leçon et en demande une nouvelle version."""

import copy
from typing import Any

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.ports import AIInvalidOutput
from app.ai.providers.fake import FakeProvider, material_output, requested_ids
from app.ai.schemas import MaterialBatchOutput
from app.db.models import AiRun, KnowledgeMastery
from tests.api.helpers import auth, family_with_device, register, upload_lesson
from tests.api.test_dashboard import revise
from tests.api.test_sessions import now  # noqa: F401  (fixture)

SORTING = {
    "prompt": "Range chaque mot : voyelle ou consonne ?",
    "categories": [
        {"name": "Voyelle", "members": ["a", "o"]},
        {"name": "Consonne", "members": ["b", "t"]},
    ],
}


async def test_the_parent_reads_and_reworks_the_questions(
    client: AsyncClient,
    db: AsyncSession,
    fake_llm: FakeProvider,
    now: Any,  # noqa: F811
) -> None:
    family = await family_with_device(client)
    parent, token, child_id = family["parent"], family["device"], family["child"]["id"]
    lesson = await upload_lesson(client, token)
    await revise(client, db, token, lesson["id"], lambda _: True)
    masteries = await db.scalar(select(func.count()).select_from(KnowledgeMastery))
    url = f"/v1/children/{child_id}/lessons/{lesson['id']}/content"

    content = (await client.get(url, headers=auth(parent))).json()
    assert content["grade"] == "CM1" and content["notions"]
    notion = content["notions"][0]
    assert any(b["title"] == "❓ Questions à choix" and "✅" in b["lines"][0] for b in notion["blocks"])

    # Le parent trouve la notion trop difficile : l'IA refait ses questions, avec sa remarque.
    def better(attempt: int, text: str) -> MaterialBatchOutput:
        ids = requested_ids(text)
        material = {k: copy.deepcopy(fake_llm.script.material[k]) | {"sorting": SORTING} for k in ids}
        return material_output(material, ids)

    fake_llm.overrides["material"] = better
    rework = f"/v1/children/{child_id}/lessons/{lesson['id']}/notions/{notion['knowledge_id']}/rework"
    r = await client.post(
        rework, json={"reason": "too_hard", "comment": "Plus simple <svp>"}, headers=auth(parent)
    )
    assert r.status_code == 200, r.text
    assert any(b["title"] == "🗂️ Jeu de tri" for b in r.json()["blocks"])
    sent = [text for stage, text in fake_llm.calls if stage == "material"][-1]
    assert "C'est trop difficile pour sa classe. Plus simple ‹svp›" in sent  # chevrons neutralisés
    assert "<remarque_parent>" in sent
    again = (await client.get(url, headers=auth(parent))).json()["notions"][0]
    assert again["blocks"] == r.json()["blocks"]
    # La progression de l'enfant n'est pas touchée ; l'appel est journalisé.
    assert await db.scalar(select(func.count()).select_from(KnowledgeMastery)) == masteries
    assert (await db.scalars(select(AiRun.stage).order_by(AiRun.created_at.desc()))).first() == "material"

    # L'IA échoue : les anciennes questions restent.
    fake_llm.overrides["material"] = AIInvalidOutput("hors schéma")
    failed = await client.post(rework, json={"reason": "unclear"}, headers=auth(parent))
    assert (failed.status_code, failed.json()["error"]["code"]) == (409, "rework_failed")
    assert (await client.get(url, headers=auth(parent))).json()["notions"][0] == again

    # « Autre » sans commentaire : rien à demander à l'IA.
    empty = await client.post(rework, json={"reason": "other"}, headers=auth(parent))
    assert empty.status_code == 422

    # Réservé au parent de cet enfant.
    assert (await client.get(url, headers=auth(token))).status_code == 403
    assert (await client.post(rework, json={"reason": "wrong"}, headers=auth(token))).status_code == 403
    stranger = (await register(client, "autre@example.fr"))["access_token"]
    assert (await client.get(url, headers=auth(stranger))).status_code == 404
    assert (await client.post(rework, json={"reason": "wrong"}, headers=auth(stranger))).status_code == 404
