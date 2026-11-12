"""Étape 24b : le parent permet la recherche de sources ; les notions sans exemple reçoivent une
explication tirée d'un site éducatif, proposée par « Je n'ai pas compris »."""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import AiRun, KnowledgeItem
from app.services import sourced_help
from app.services.web_sources import WebSources
from tests.api.helpers import auth, family_with_device, upload_lesson

SEARX = "http://recherche:8080"
PAGE = "https://fr.vikidia.org/wiki/R%C3%A9volution_fran%C3%A7aise"
HTML = (
    "<html><head><title>Révolution française — Vikidia</title></head><body>"
    "<p>La Révolution française est une période de grands changements en France, pendant laquelle "
    "le peuple réclame plus de justice et d'égalité entre les citoyens.</p></body></html>"
)


def internet(request: httpx.Request) -> httpx.Response:
    if request.url.host == "recherche":
        return httpx.Response(200, json={"results": [{"url": PAGE, "title": "Révolution française"}]})
    return httpx.Response(200, text=HTML, headers={"content-type": "text/html; charset=utf-8"})


@pytest.fixture
def search_engine(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    settings: Settings = app.state.settings
    app.state.settings = settings.model_copy(update={"web_search_url": SEARX})

    def fake_web(url: str, sites: Any, library: Any = None) -> WebSources:
        client = httpx.AsyncClient(transport=httpx.MockTransport(internet))
        return WebSources(url, sites, client=client, library=library)

    monkeypatch.setattr(sourced_help, "WebSources", fake_web)


async def test_the_parent_decides(app: FastAPI, client: AsyncClient) -> None:
    parent = (await family_with_device(client))["parent"]
    r = await client.put("/v1/parent/ai/sources", json={"enabled": True}, headers=auth(parent))
    assert r.status_code == 409 and r.json()["error"]["code"] == "web_search_unavailable"
    settings = (await client.get("/v1/parent/ai", headers=auth(parent))).json()
    assert (settings["web_sources"], settings["web_sources_available"]) == (False, False)


async def test_sourced_help_for_notions_without_example(
    client: AsyncClient, db: AsyncSession, search_engine: None
) -> None:
    family = await family_with_device(client)
    token = family["device"]
    # Sans l'accord du parent : rien n'est cherché.
    await upload_lesson(client, token)
    assert await db.scalar(select(AiRun.id).where(AiRun.stage == "sources")) is None

    r = await client.put("/v1/parent/ai/sources", json={"enabled": True}, headers=auth(family["parent"]))
    assert r.status_code == 200 and r.json()["web_sources"] and r.json()["web_sources_available"]
    lesson = await upload_lesson(client, token)
    helped = list(await db.scalars(select(KnowledgeItem).where(KnowledgeItem.external_help.is_not(None))))
    assert len(helped) == sourced_help.MAX_NOTIONS
    stored = helped[0].external_help
    assert stored is not None and stored["origin"] == "SOURCE_EXTERNAL_KNOWLEDGE"
    assert stored["sources"][0]["url"] == PAGE and stored["quotes"]
    assert {r.stage for r in await db.scalars(select(AiRun).where(AiRun.stage == "sources"))} == {"sources"}

    # « Je n'ai pas compris » : l'explication sourcée arrive au niveau 3.
    session = (await client.post(f"/v1/lessons/{lesson['id']}/sessions", json={}, headers=auth(token))).json()
    helped_ids = {str(k.id) for k in helped}
    kinds: list[str] = []
    for item in session["items"]:
        if not item["help_available"] or not set(item["knowledge_ids"]) & helped_ids:
            continue
        url = f"/v1/sessions/{session['id']}/items/{item['id']}/help"
        step: dict[str, Any] = {"last": False}
        while not step["last"]:
            step = (await client.post(url, headers=auth(token))).json()
            kinds.append(step["kind"])
            if step["kind"] == "sourced":
                assert step["level"] == 3 and step["lines"] == ["📚 En plus de ta leçon — fr.vikidia.org"]
    assert "sourced" in kinds
