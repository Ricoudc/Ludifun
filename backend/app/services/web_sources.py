"""Recherche de sources sur Internet (étape 24) : Ludifun cherche, l'IA lit.

Le moteur est SearXNG, installé à côté de Ludifun (docker compose, profil « recherche ») : pas de
compte, pas de publicité, pas de pistage. Seule la question part sur Internet (la notion, jamais
le prénom de l'enfant ni sa photo). Seules les pages en https des sites autorisés sont lues ;
une redirection vers un autre site est refusée.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from html.parser import HTMLParser

import httpx

from app.domain.sources import DEFAULT_SITES, EXCERPT_CHARS, Excerpt, allowed, best_excerpts
from app.services.library import Library

logger = logging.getLogger("ludifun.sources")

TIMEOUT_S = 10.0
MAX_PAGE_BYTES = 2 * 1024 * 1024
MAX_PAGES = 4  # pages lues par question
USER_AGENT = "Ludifun/1.0 (coach de revision ; recherche de sources educatives)"


class SearchUnavailable(Exception):
    """Moteur de recherche injoignable ou mal réglé (format json non autorisé…)."""


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str


class _TextExtractor(HTMLParser):
    """Texte lisible d'une page : paragraphes, listes, titres ; sans menus, scripts ni pieds de
    page. Suffisant pour Vikidia, Wikipédia et les sites institutionnels."""

    SKIP = frozenset(
        {"script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg", "table"}
    )
    BLOCKS = frozenset({"p", "li", "h1", "h2", "h3", "h4", "dd", "dt", "blockquote", "br", "div", "section"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._skipping = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self._skipping += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skipping:
            self._skipping -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif not self._skipping:
            self.parts.append(data)


def page_text(html: str) -> tuple[str, str]:
    """(titre, texte) d'une page HTML ; les références « [1] » de Wikipédia sont retirées."""
    extractor = _TextExtractor()
    extractor.feed(html)
    lines = (" ".join(line.split()) for line in "".join(extractor.parts).split("\n"))
    text = "\n".join(line for line in lines if line)
    for mark in ("[modifier | modifier le code]", "[modifier]"):
        text = text.replace(mark, "")
    return " ".join(extractor.title.split()), text


class WebSources:
    def __init__(
        self,
        search_url: str,
        sites: Sequence[str] = DEFAULT_SITES,
        client: httpx.AsyncClient | None = None,
        library: Library | None = None,
    ) -> None:
        self.search_url = search_url.rstrip("/")
        self.sites = tuple(sites)
        self.library = library  # étape 24d : pages déjà lues, et recherche sans Internet
        self._client = client or httpx.AsyncClient(
            timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT}, follow_redirects=False
        )

    async def search(self, question: str, limit: int = MAX_PAGES) -> list[SearchResult]:
        """Résultats des sites autorisés : d'abord une recherche libre, puis, s'il en manque,
        une recherche limitée à chaque site, dans l'ordre de préférence."""
        found: dict[str, SearchResult] = {}
        queries = [question] + [f"{question} site:{site}" for site in self.sites[:3]]
        for query in queries:
            for result in await self._query(query):
                if allowed(result.url, self.sites) and result.url not in found:
                    found[result.url] = result
            if len(found) >= limit:
                break
        preference = {site: rank for rank, site in enumerate(self.sites)}

        def rank(result: SearchResult) -> int:
            host = result.url.split("/")[2].lower()
            return min((r for s, r in preference.items() if host == s or host.endswith("." + s)), default=99)

        return sorted(found.values(), key=rank)[:limit]

    async def _query(self, query: str) -> list[SearchResult]:
        try:
            response = await self._client.get(
                f"{self.search_url}/search",
                params={"q": query, "format": "json", "language": "fr", "safesearch": 2},
            )
        except httpx.HTTPError as exc:
            raise SearchUnavailable(f"moteur de recherche injoignable ({type(exc).__name__})") from exc
        if response.status_code == 403:
            raise SearchUnavailable("le moteur refuse le format json (search.formats dans settings.yml)")
        if response.status_code != 200:
            raise SearchUnavailable(f"moteur de recherche : erreur {response.status_code}")
        results = response.json().get("results", [])
        return [
            SearchResult(str(r["url"]), str(r.get("title") or ""))
            for r in results
            if isinstance(r, dict) and r.get("url")
        ]

    async def fetch(self, url: str) -> tuple[str, str] | None:
        """(titre, texte) d'une page autorisée ; None si elle n'est pas lisible."""
        if not allowed(url, self.sites):
            return None
        try:
            async with self._client.stream("GET", url) as response:
                kind = response.headers.get("content-type", "")
                if response.status_code != 200 or "html" not in kind:
                    return None
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > MAX_PAGE_BYTES:
                        return None
                encoding = response.encoding or "utf-8"
        except httpx.HTTPError as exc:
            logger.info("Page illisible %s : %s", url, type(exc).__name__)
            return None
        return page_text(body.decode(encoding, errors="replace"))

    async def pages(self, question: str, limit: int = MAX_PAGES) -> list[tuple[str, str, str]]:
        """(adresse, titre, texte) des pages trouvées. Avec une bibliothèque : chaque page lue y
        est gardée, une page déjà gardée n'est pas relue, et si le moteur ou Internet ne répond
        pas, la recherche se fait dans la bibliothèque seule."""
        found: dict[str, tuple[str, str, str]] = {}
        try:
            results = await self.search(question, limit)
        except SearchUnavailable:
            if self.library is None:
                raise
            logger.info("Moteur de recherche injoignable : bibliothèque du PC seulement")
            results = []
        for result in results:
            read = await self.library.get(result.url) if self.library is not None else None
            if read is None:
                read = await self.fetch(result.url)
                if read is not None and read[1] and self.library is not None:
                    await self.library.save(result.url, read[0] or result.title, read[1])
            if read is not None and read[1]:
                found[result.url] = (result.url, read[0] or result.title, read[1])
        if self.library is not None and len(found) < limit:
            for url, title, text in await self.library.search(question, limit):
                if allowed(url, self.sites):
                    found.setdefault(url, (url, title, text))
        return list(found.values())[:limit]

    async def excerpts(self, question: str, count: int = 3, max_chars: int = EXCERPT_CHARS) -> list[Excerpt]:
        """Les meilleurs extraits des pages trouvées, numérotés à partir de 1."""
        return best_excerpts(question, await self.pages(question), count, max_chars)
