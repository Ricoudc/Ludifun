"""Bibliothèque sur le PC (étape 24d) : la remplir à l'avance, voir ce qu'elle contient, y chercher.

    docker compose exec api python -m app.tools.library depart          # premier lot (Vikidia)
    docker compose exec api python -m app.tools.library ajouter https://fr.vikidia.org/wiki/Volcan
    docker compose exec api python -m app.tools.library ajouter --liste mes_pages.txt
    docker compose exec api python -m app.tools.library etat
    docker compose exec api python -m app.tools.library chercher "Pourquoi les volcans entrent en éruption ?"

Seules les pages des sites autorisés (LUDIFUN_WEB_SOURCES) sont gardées. Remplir demande Internet
une fois ; chercher, non. La bibliothèque se remplit aussi toute seule quand Ludifun cherche des
sources.
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import TextIO

from app.config import Settings, get_settings
from app.db.base import Database
from app.domain.sources import allowed
from app.services.library import Library
from app.services.web_sources import WebSources

STARTER = Path(__file__).resolve().parents[1] / "library" / "depart.txt"


def read_list(path: Path) -> list[str]:
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    return [line for line in lines if line and not line.startswith("#")]


async def add(urls: list[str], settings: Settings, out: TextIO, web: WebSources | None = None) -> int:
    library = Library(Database(settings.database_url)) if web is None else web.library
    assert library is not None
    web = web or WebSources(settings.web_search_url or "", settings.web_sites, library=library)
    saved = 0
    for url in urls:
        if not allowed(url, web.sites):
            print(f"  ✗ {url} : site non autorisé", file=out)
            continue
        page = await web.fetch(url)
        if page is None or not page[1]:
            print(f"  ✗ {url} : page introuvable ou illisible", file=out)
            continue
        await library.save(url, page[0], page[1])
        saved += 1
        print(f"  ✓ {page[0] or url}", file=out)
    print(f"{saved} page(s) ajoutée(s) sur {len(urls)}.", file=out)
    return 0 if saved else 1


async def state(library: Library, out: TextIO) -> int:
    counts = await library.count_by_site()
    if not counts:
        print("Bibliothèque vide : python -m app.tools.library depart", file=out)
        return 0
    for site, count in counts.items():
        print(f"  {site} : {count} page(s)", file=out)
    print(f"Total : {sum(counts.values())} page(s).", file=out)
    return 0


async def search(library: Library, question: str, out: TextIO) -> int:
    pages = await library.search(question)
    if not pages:
        print("Rien trouvé dans la bibliothèque.", file=out)
        return 1
    for url, title, text in pages:
        print(f"  {title} — {url}\n    {text[:200]}…", file=out)
    return 0


def main(argv: list[str] | None = None, out: TextIO = sys.stdout) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.tools.library", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("depart", help="ajouter le premier lot de pages (Vikidia, CP à 3e)")
    adding = commands.add_parser("ajouter", help="ajouter des pages par leur adresse")
    adding.add_argument("urls", nargs="*")
    adding.add_argument("--liste", type=Path, help="fichier texte : une adresse par ligne")
    commands.add_parser("etat", help="nombre de pages par site")
    finding = commands.add_parser("chercher", help="chercher dans la bibliothèque (sans Internet)")
    finding.add_argument("question")
    args = parser.parse_args(argv)
    settings = get_settings()
    library = Library(Database(settings.database_url))
    if args.command == "depart":
        return asyncio.run(add(read_list(STARTER), settings, out))
    if args.command == "ajouter":
        urls = list(args.urls) + (read_list(args.liste) if args.liste else [])
        if not urls:
            parser.error("donner au moins une adresse, ou --liste")
        return asyncio.run(add(urls, settings, out))
    if args.command == "etat":
        return asyncio.run(state(library, out))
    return asyncio.run(search(library, args.question, out))


if __name__ == "__main__":
    sys.exit(main())
