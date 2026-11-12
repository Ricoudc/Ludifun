"""Étape 24d : la bibliothèque sur le PC garde les pages lues et répond sans Internet."""

import io
from collections.abc import AsyncIterator, Callable

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings
from app.db.base import Database
from app.services.library import Library
from app.services.web_sources import SearchUnavailable, WebSources
from app.tools import library as tool
from app.tools.sources import run as sources_tool
from tests.conftest import TEST_DATABASE_URL, truncate_all

SEARX = "http://recherche:8080"
VOLCAN = "https://fr.vikidia.org/wiki/Volcan"
HTML = (
    "<html><head><title>Volcan — Vikidia</title></head><body><p>Un volcan est un relief formé par "
    "la remontée du magma. Lors d'une éruption, la lave sort par le cratère et coule sur les "
    "pentes.</p></body></html>"
)


@pytest.fixture
async def library(engine: AsyncEngine) -> AsyncIterator[Library]:
    database = Database(TEST_DATABASE_URL)
    yield Library(database)
    await database.dispose()
    await truncate_all(engine)


def web(library: Library, handler: Callable[[httpx.Request], httpx.Response]) -> WebSources:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return WebSources(SEARX, client=client, library=library)


def online(requests: list[str]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.host == "recherche":
            return httpx.Response(200, json={"results": [{"url": VOLCAN, "title": "Volcan"}]})
        return httpx.Response(200, text=HTML, headers={"content-type": "text/html"})

    return handler


def offline(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("pas d'Internet")


async def test_pages_read_once_are_kept_and_found_offline(library: Library) -> None:
    requests: list[str] = []
    first = await web(library, online(requests)).excerpts("Comment se forme un volcan ?")
    assert first and first[0].url == VOLCAN
    assert await library.count_by_site() == {"fr.vikidia.org": 1}

    # Page déjà gardée : pas relue sur Internet.
    requests.clear()
    await web(library, online(requests)).excerpts("Comment se forme un volcan ?")
    assert VOLCAN not in requests

    # Sans Internet : la bibliothèque répond seule (racines françaises : « éruptions » → « éruption »).
    again = await web(library, offline).excerpts("Que se passe-t-il pendant les éruptions ?")
    assert again and again[0].url == VOLCAN and "éruption" in again[0].text
    assert await library.search("photosynthèse chlorophylle") == []

    # Sans bibliothèque ni Internet : l'erreur remonte comme avant.
    with pytest.raises(SearchUnavailable):
        await WebSources(SEARX, client=httpx.AsyncClient(transport=httpx.MockTransport(offline))).pages(
            "volcan"
        )


async def test_the_library_tool(library: Library) -> None:
    out = io.StringIO()
    sources = web(library, online([]))
    code = await tool.add([VOLCAN, "https://forum.example/volcan"], Settings(), out, sources)
    assert code == 0 and "✓ Volcan — Vikidia" in out.getvalue() and "site non autorisé" in out.getvalue()
    out = io.StringIO()
    await tool.state(library, out)
    assert "fr.vikidia.org : 1 page(s)" in out.getvalue()
    out = io.StringIO()
    assert await tool.search(library, "éruption du volcan", out) == 0 and VOLCAN in out.getvalue()
    assert all(u.startswith("https://fr.vikidia.org/wiki/") for u in tool.read_list(tool.STARTER))

    # L'outil de recherche de sources marche aussi hors ligne, grâce à la bibliothèque.
    out = io.StringIO()
    settings = Settings(ai_provider="fake")
    assert (
        await sources_tool(
            "Pourquoi un volcan entre en éruption ?", "CE2", True, settings, out, web(library, offline)
        )
        == 0
    )
    assert "📚 En plus de ta leçon" in out.getvalue()
