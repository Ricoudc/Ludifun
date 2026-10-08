"""Étape 29 : avec l'accord du parent, des questions tirées des sites de confiance s'ajoutent au
matériel de la leçon ; le parent les voit à part, avec leur source ; sans accord, rien."""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import AiRun, KnowledgeMaterial
from app.services import sourced_help, sourced_practice
from app.services.web_sources import WebSources
from tests.api.helpers import auth, family_with_device, upload_lesson
from tests.api.test_sourced_help import SEARX, internet


@pytest.fixture
def search_engine(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    settings: Settings = app.state.settings
    app.state.settings = settings.model_copy(update={"web_search_url": SEARX})

    def fake_web(url: str, sites: Any, library: Any = None) -> WebSources:
        client = httpx.AsyncClient(transport=httpx.MockTransport(internet))
        return WebSources(url, sites, client=client, library=library)

    monkeypatch.setattr(sourced_help, "WebSources", fake_web)
    monkeypatch.setattr(sourced_practice, "WebSources", fake_web)


def sourced_questions(materials: list[KnowledgeMaterial]) -> list[dict[str, Any]]:
    return [q for m in materials for q in m.material.get("questions", []) if q.get("source")]


async def test_questions_from_trusted_sites_join_the_lesson(
    client: AsyncClient, db: AsyncSession, search_engine: None
) -> None:
    family = await family_with_device(client)
    # Sans l'accord du parent : rien n'est cherché, rien n'est ajouté.
    await upload_lesson(client, family["device"])
    assert await db.scalar(select(AiRun.id).where(AiRun.stage == "practice")) is None

    await client.put("/v1/parent/ai/sources", json={"enabled": True}, headers=auth(family["parent"]))
    lesson = await upload_lesson(client, family["device"])
    runs = list(
        await db.scalars(select(AiRun).where(AiRun.stage == "practice", AiRun.lesson_id == lesson["id"]))
    )
    assert runs and all(r.prompt_version == "v1" for r in runs)
    materials = list(await db.scalars(select(KnowledgeMaterial)))
    added = sourced_questions(materials)
    # La même question pour plusieurs notions : gardée une seule fois (doublons retirés).
    assert len(added) == 1
    source = added[0]["source"]
    assert source["site"] == "fr.vikidia.org" and source["quote"] in internet_text()
    assert added[0]["answer"] in source["quote"]
    assert any("double" in w for r in runs for w in r.warnings)

    # Le parent les voit à part, avec la phrase qui prouve la réponse.
    content = (
        await client.get(
            f"/v1/children/{family['child']['id']}/lessons/{lesson['id']}/content",
            headers=auth(family["parent"]),
        )
    ).json()
    titles = [b["title"] for n in content["notions"] for b in n["blocks"]]
    assert "📚 Questions tirées des sites de confiance" in titles


def internet_text() -> str:
    from tests.api.test_sourced_help import HTML

    return HTML
