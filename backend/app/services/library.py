"""Bibliothèque sur le PC (étape 24d) : les pages de sites autorisés déjà lues, pour chercher des
sources sans Internet.

Elle se remplit toute seule (chaque page lue par la recherche y est gardée) et peut être remplie
à l'avance (`python -m app.tools.library`). La recherche utilise le plein texte en français de
PostgreSQL (racines des mots : « réunit » trouve « réunir »), sans index : une bibliothèque
familiale compte quelques milliers de pages au plus.
"""

from datetime import UTC, datetime

from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.postgresql import insert

from app.db.base import Database
from app.db.models import LibraryPage
from app.domain.sources import search_words, site_of

MAX_TEXT = 200_000  # signes gardés par page


def _document() -> object:
    return func.to_tsvector(literal_column("'french'::regconfig"), LibraryPage.title + " " + LibraryPage.text)


class Library:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def save(self, url: str, title: str, text: str) -> None:
        values = {
            "url": url,
            "site": site_of(url),
            "title": title[:300],
            "text": text[:MAX_TEXT],
            "fetched_at": datetime.now(UTC),
        }
        statement = insert(LibraryPage).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[LibraryPage.url],
            set_={k: statement.excluded[k] for k in ("site", "title", "text", "fetched_at")},
        )
        async with self.database.sessionmaker() as session:
            await session.execute(statement)
            await session.commit()

    async def get(self, url: str) -> tuple[str, str] | None:
        async with self.database.sessionmaker() as session:
            page = await session.get(LibraryPage, url)
        return (page.title, page.text) if page is not None else None

    async def search(self, question: str, limit: int = 4) -> list[tuple[str, str, str]]:
        """(adresse, titre, texte) des pages qui partagent le plus de mots avec la question."""
        words = search_words(question)
        if not words:
            return []
        query = func.websearch_to_tsquery(literal_column("'french'::regconfig"), " or ".join(words))
        document = _document()
        rank = func.ts_rank(document, query)
        async with self.database.sessionmaker() as session:
            rows = await session.execute(
                select(LibraryPage.url, LibraryPage.title, LibraryPage.text)
                .where(document.op("@@")(query))  # type: ignore[attr-defined]
                .order_by(rank.desc())
                .limit(limit)
            )
            return [(url, title, text) for url, title, text in rows]

    async def count_by_site(self) -> dict[str, int]:
        async with self.database.sessionmaker() as session:
            rows = await session.execute(
                select(LibraryPage.site, func.count()).group_by(LibraryPage.site).order_by(LibraryPage.site)
            )
            return {site: count for site, count in rows}
