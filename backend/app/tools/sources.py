"""Essaie la recherche de sources depuis le terminal (étape 24) : Ludifun cherche, l'IA lit.

    docker compose exec api python -m app.tools.sources "Pourquoi Louis XVI réunit-il les États généraux ?"
    uv run python -m app.tools.sources "Qu'est-ce qu'un volcan ?" --classe CE2
    uv run python -m app.tools.sources "le cycle de l'eau" --sans-ia

Affiche les pages trouvées sur les sites autorisés, les extraits donnés à l'IA, puis sa réponse
et les citations vérifiées (ou pourquoi la réponse a été écartée). Rien n'est enregistré.
Il faut le moteur SearXNG (profil « recherche » du docker compose, LUDIFUN_WEB_SEARCH_URL).
"""

import argparse
import asyncio
import sys
from typing import TextIO

from app.ai.factory import build_llm
from app.config import Settings, get_settings
from app.services.sourced_answer import SourcedAnswerer
from app.services.web_sources import SearchUnavailable, WebSources

NOT_ENABLED = (
    "Recherche de sources désactivée : ajoutez dans .env\n"
    "  COMPOSE_PROFILES=recherche\n"
    "  LUDIFUN_WEB_SEARCH_URL=http://recherche:8080\n"
    "puis relancez Demarrer-Ludifun.bat."
)


async def run(
    question: str,
    grade: str,
    with_ai: bool,
    settings: Settings,
    out: TextIO,
    sources: WebSources | None = None,
) -> int:
    if sources is None:
        if not settings.web_search_url:
            print(NOT_ENABLED, file=out)
            return 2
        sources = WebSources(settings.web_search_url, settings.web_sites)
    print(f"Question : {question}\nSites autorisés : {', '.join(sources.sites)}\n", file=out)
    try:
        excerpts = await sources.excerpts(question)
    except SearchUnavailable as exc:
        print(f"Recherche impossible : {exc}", file=out)
        return 1
    if not excerpts:
        print("Aucun extrait trouvé sur les sites autorisés.", file=out)
        return 1
    for e in excerpts:
        print(
            f"[{e.number}] {e.title} — {e.url}\n    {e.text[:300]}{'…' if len(e.text) > 300 else ''}\n",
            file=out,
        )
    if not with_ai:
        return 0

    llm = build_llm(settings)
    print(f"L'IA lit les extraits ({llm.name} · {llm.model_for('sources')})…\n", file=out)
    done = await SourcedAnswerer(llm).answer(question, grade, excerpts)
    run_ = done.run
    print(f"Durée : {run_.latency_ms / 1000:.0f} s · statut : {run_.status}", file=out)
    if done.answer is None:
        reason = run_.warnings[0] if run_.warnings else "réponse écartée"
        print(f"Pas de réponse montrée à l'enfant : {reason}", file=out)
        return 1
    print(f"\n📚 En plus de ta leçon : {done.answer.text}\n", file=out)
    for quote in done.answer.quotes:
        print(f"  « {quote.text} » (source {quote.source})", file=out)
    print("\nSources :", file=out)
    for e in done.answer.sources:
        print(f"  [{e.number}] {e.site} — {e.url}", file=out)
    return 0


def main(argv: list[str] | None = None, out: TextIO = sys.stdout) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.tools.sources", description=__doc__.split("\n")[0])
    parser.add_argument(
        "question", help="la question ou la notion, par exemple « les États généraux de 1789 »"
    )
    parser.add_argument("--classe", default="CM1", help="classe de l'élève (défaut : CM1)")
    parser.add_argument("--sans-ia", action="store_true", help="seulement chercher et afficher les extraits")
    args = parser.parse_args(argv)
    return asyncio.run(run(args.question, args.classe, not args.sans_ia, get_settings(), out))


if __name__ == "__main__":
    sys.exit(main())
