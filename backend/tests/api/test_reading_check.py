"""Étape 24c, de bout en bout : une date de la photo que les sources contredisent devient un
passage « Peux-tu vérifier ? » ; après la réponse de l'enfant, l'analyse reprend sans reboucler."""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.config import Settings
from app.services import reading_check
from app.services.web_sources import WebSources
from tests.api.helpers import auth, family_with_device, upload_lesson

SEARX = "http://recherche:8080"
PAGES = {
    "https://fr.vikidia.org/wiki/Revolution": "La Révolution française commence en 1798 à Paris.",
    "https://fr.wikipedia.org/wiki/Revolution": "En 1798, la Révolution française éclate.",
}


def internet(request: httpx.Request) -> httpx.Response:
    if request.url.host == "recherche":
        return httpx.Response(200, json={"results": [{"url": u, "title": "Révolution"} for u in PAGES]})
    body = f"<html><body><p>{PAGES[str(request.url)]}</p></body></html>"
    return httpx.Response(200, text=body, headers={"content-type": "text/html"})


@pytest.fixture
def search_engine(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    settings: Settings = app.state.settings
    app.state.settings = settings.model_copy(update={"web_search_url": SEARX})

    def fake_web(url: str, sites: Any, library: Any = None) -> WebSources:
        client = httpx.AsyncClient(transport=httpx.MockTransport(internet))
        return WebSources(url, sites, client=client, library=library)

    monkeypatch.setattr(reading_check, "WebSources", fake_web)


async def test_a_date_contradicted_by_sources_is_checked_by_the_child(
    client: AsyncClient, search_engine: None
) -> None:
    # Ici les « sources » disent 1798 et la photo 1789 : le mécanisme compte, pas l'histoire.
    family = await family_with_device(client)
    token = family["device"]
    ready = await upload_lesson(client, token)
    assert ready["status"] == "ready"  # parent pas d'accord : aucune vérification

    await client.put("/v1/parent/ai/sources", json={"enabled": True}, headers=auth(family["parent"]))
    lesson = await upload_lesson(client, token)
    assert lesson["status"] == "needs_review"
    (item,) = [i for i in lesson["review"] if i["read_text"] == "1789"]
    assert "1798" not in item["context"]  # jamais la réponse soufflée

    answers = [{"item_id": i["id"], "status": "confirmed"} for i in lesson["review"]]
    r = await client.post(
        f"/v1/lessons/{lesson['id']}/review", json={"answers": answers}, headers=auth(token)
    )
    assert r.status_code == 202
    after = (await client.get(f"/v1/lessons/{lesson['id']}", headers=auth(token))).json()
    assert after["status"] == "ready"  # texte vérifié : pas de nouvelle vérification
