"""Ressources des sites de confiance (étape 30) : préparées après l'analyse, ouvertes dans
l'application.

Seulement si le parent l'a permis (`families.web_sources`) et si le serveur ne les a pas
désactivées (`LUDIFUN_RESOURCES`). En arrière-plan, la leçon est déjà prête ; un site
injoignable ne touche jamais la leçon : il n'apporte simplement rien.

- MathALÉA : le catalogue public (référentiel JSON) est lu une fois par jour ; les exercices de la
  classe qui parlent de la leçon sont proposés (`app.domain.resources.choose_mathalea`).
- Vikidia : recherche par l'API du wiki, lecture des quiz ; la page du quiz est proposée, et ses
  questions à choix qui parlent d'une notion rejoignent le matériel (mêmes contrôles que les
  questions de la leçon, sans doublon, avec source et licence).
- Lumni : recherche par le moteur du serveur (SearXNG), limitée à lumni.fr ; vidéos et quiz
  proposés tels quels.

Seuls le titre de la leçon et les noms des notions partent vers ces sites : jamais le prénom de
l'enfant, sa photo ni le texte de sa leçon.
"""

import logging
import time
import uuid
from typing import Any

import httpx
from sqlalchemy import select

from app.config import Settings
from app.db import models as db
from app.db.base import Database
from app.domain.duplicates import deduplicate
from app.domain.knowledge import KnowledgeMaterial, QuestionSource
from app.domain.resources import (
    LICENCES,
    PER_PROVIDER,
    CatalogueEntry,
    Provider,
    Resource,
    ResourceKind,
    catalogue_entries,
    choose_mathalea,
    lumni_resource,
    parse_quiz,
    quiz_material,
    vikidia_page_url,
)
from app.domain.validation import check_question, needs_picture, needs_support
from app.services.lesson_store import load_units
from app.services.web_sources import SearchUnavailable, WebSources

logger = logging.getLogger("ludifun.sources")

USER_AGENT = "Ludifun/1.0 (application de revision familiale)"
CATALOGUE_TTL_S = 24 * 3600
VIKIDIA_PAGES = 5  # pages lues au plus par leçon
LUMNI_SITES = ("www.lumni.fr", "lumni.fr")

_catalogue: tuple[float, list[CatalogueEntry]] | None = None


def new_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=20, headers={"User-Agent": USER_AGENT}, follow_redirects=True)


async def mathalea_catalogue(client: httpx.AsyncClient, settings: Settings) -> list[CatalogueEntry]:
    """Le catalogue de MathALÉA, gardé un jour en mémoire."""
    global _catalogue
    if _catalogue is not None and time.monotonic() - _catalogue[0] < CATALOGUE_TTL_S:
        return _catalogue[1]
    response = await client.get(settings.mathalea_catalogue_url)
    response.raise_for_status()
    data = response.json()
    entries = catalogue_entries(data) if isinstance(data, dict) else []
    _catalogue = (time.monotonic(), entries)
    return entries


def forget_catalogue() -> None:
    global _catalogue
    _catalogue = None


async def vikidia_quizzes(client: httpx.AsyncClient, settings: Settings, query: str) -> list[tuple[str, str]]:
    """(titre, wikitexte) des pages de Vikidia qui ont un quiz sur le sujet."""
    found = await client.get(
        settings.vikidia_api_url,
        params={
            "action": "query",
            "list": "search",
            "srsearch": f"quiz {query}",
            "srnamespace": "*",
            "srlimit": 10,
            "format": "json",
        },
    )
    found.raise_for_status()
    titles = [str(r["title"]) for r in found.json().get("query", {}).get("search", []) if r.get("title")]
    pages: list[tuple[str, str]] = []
    for title in titles[: VIKIDIA_PAGES * 2]:
        page = await client.get(
            settings.vikidia_api_url,
            params={
                "action": "parse",
                "page": title,
                "prop": "wikitext",
                "format": "json",
                "formatversion": 2,
            },
        )
        if page.status_code != 200:
            continue
        text = page.json().get("parse", {}).get("wikitext", "")
        if isinstance(text, str) and "<quiz" in text.lower():
            pages.append((title, text))
        if len(pages) == VIKIDIA_PAGES:
            break
    return pages


async def family_allows(session: Any, settings: Settings, lesson_id: uuid.UUID) -> bool:
    if not settings.resources:
        return False
    allowed = await session.scalar(
        select(db.Family.web_sources)
        .join(db.Child, db.Child.family_id == db.Family.id)
        .join(db.Lesson, db.Lesson.child_id == db.Child.id)
        .where(db.Lesson.id == lesson_id)
    )
    return bool(allowed)


async def prepare(
    database: Database,
    settings: Settings,
    lesson_id: uuid.UUID,
    client: httpx.AsyncClient | None = None,
    web: WebSources | None = None,
) -> int:
    """Cherche les ressources de la leçon ; renvoie le nombre de ressources proposées."""
    async with database.sessionmaker() as session:
        if not await family_allows(session, settings, lesson_id):
            return 0
        lesson = await session.get(db.Lesson, lesson_id)
        if lesson is None or lesson.status != "ready":
            return 0
        units = await load_units(session, lesson)
        notions = [u.item for u in sorted(units.units, key=lambda u: -u.item.importance)]
        query = lesson.title or (notions[0].label if notions else "")
        if not query:
            return 0
        http = client or new_client()
        resources: list[Resource] = []

        # MathALÉA : des exercices notés, de la classe de l'enfant.
        try:
            catalogue = await mathalea_catalogue(http, settings)
            resources += choose_mathalea(catalogue, lesson.subject, lesson.grade, lesson.title, notions)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("MathALÉA injoignable : %s", type(exc).__name__)

        # Vikidia : les quiz, et leurs questions qui parlent d'une notion de la leçon.
        materials: dict[str, KnowledgeMaterial] = {u.id: u.material for u in units.units}
        added: dict[str, list[Any]] = {}
        try:
            for title, text in await vikidia_quizzes(http, settings, query):
                questions = parse_quiz(text)
                if not questions:
                    continue
                url = vikidia_page_url(title)
                if len([r for r in resources if r.provider is Provider.VIKIDIA]) < PER_PROVIDER:
                    resources.append(Resource(Provider.VIKIDIA, ResourceKind.QUIZ, title, url))
                source = QuestionSource(
                    site="fr.vikidia.org",
                    url=url,
                    quote=f"Quiz « {title} »",
                    licence=LICENCES[Provider.VIKIDIA],
                )
                for material in quiz_material(questions, notions):
                    question, reason = check_question(material.question)
                    if (
                        question is None
                        or reason
                        or needs_picture(question.stem)
                        or needs_support(question.stem)
                    ):
                        continue
                    added.setdefault(material.knowledge_id, []).append(
                        question.model_copy(update={"source": source})
                    )
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Vikidia injoignable : %s", type(exc).__name__)

        # Lumni : vidéos et quiz, par le moteur de recherche du serveur.
        if settings.web_search_url:
            lumni = web or WebSources(settings.web_search_url, LUMNI_SITES)
            try:
                for result in await lumni.search(f"{query} lumni"):
                    found = lumni_resource(result.url, result.title)
                    if found and len([r for r in resources if r.provider is Provider.LUMNI]) < PER_PROVIDER:
                        resources.append(found)
            except SearchUnavailable as exc:
                logger.warning("Lumni : %s", exc)
        if client is None:
            await http.aclose()

        # Les questions des quiz, sans ce que la leçon a déjà.
        kept_questions = 0
        for notion, questions in added.items():
            candidate = materials[notion].model_copy(
                update={"questions": [*materials[notion].questions, *questions]}
            )
            others = [(k, m) for k, m in materials.items() if k != notion]
            kept = deduplicate([(notion, candidate)], lambda _, __: True, already=others)[notion].material
            new = len(kept.questions) - len(materials[notion].questions)
            row = await session.get(db.KnowledgeMaterial, units.key_to_id[notion]) if new > 0 else None
            if row is not None:
                row.material = kept.model_dump(mode="json")
                materials[notion] = kept
                kept_questions += new

        # Les ressources, sans toucher à celles déjà là (masquées par le parent, scores).
        existing = {
            r.url
            for r in await session.scalars(
                select(db.LessonResource).where(db.LessonResource.lesson_id == lesson_id)
            )
        }
        new_resources = [r for r in resources if r.url not in existing]
        for position, resource in enumerate(new_resources, start=len(existing)):
            session.add(
                db.LessonResource(
                    lesson_id=lesson_id,
                    provider=resource.provider.value,
                    kind=resource.kind.value,
                    title=resource.title[:200],
                    url=resource.url,
                    position=position,
                )
            )
        await session.commit()
        if new_resources or kept_questions:
            logger.info(
                "Leçon %s : %d ressource(s) des sites de confiance, %d question(s) de quiz",
                lesson_id,
                len(new_resources),
                kept_questions,
            )
        return len(new_resources)
