"""Vérification des dates lues sur une photo avec des sources (étape 24c).

Après l'analyse d'une photo, pour les notions importantes qui contiennent une année, Ludifun lit
quelques pages de sites autorisés et compare les années (`app.domain.reading_check`). Une année
lue probablement de travers devient un passage « Peux-tu vérifier ? ». Seulement si le parent a
permis la recherche de sources ; un moteur injoignable ne bloque jamais la leçon.
"""

import logging

from app.ai.schemas import OcrResult
from app.config import Settings
from app.db.base import Database
from app.domain.knowledge import LessonAnalysis
from app.domain.ocr_review import Uncertain
from app.domain.reading_check import doubtful_years, review_items, years
from app.services.lesson_pipeline import ReadingCheck
from app.services.library import Library
from app.services.web_sources import SearchUnavailable, WebSources

logger = logging.getLogger("ludifun.sources")

MAX_NOTIONS = 3  # notions datées vérifiées par leçon (les plus importantes)
PAGES = 3  # pages lues par notion


def for_settings(settings: Settings, database: Database) -> ReadingCheck:
    assert settings.web_search_url is not None
    library = Library(database)
    return make_reading_check(WebSources(settings.web_search_url, settings.web_sites, library=library))


def make_reading_check(web: WebSources) -> ReadingCheck:
    async def check(ocr: OcrResult, analysis: LessonAnalysis) -> list[Uncertain]:
        dated = sorted(
            (k for k in analysis.knowledge if years(f"{k.label} {k.statement}")),
            key=lambda k: -k.importance,
        )[:MAX_NOTIONS]
        title = analysis.lesson.title if analysis.lesson else ""
        doubts = []
        for item in dated:
            try:
                pages = await web.pages(f"{item.label} {title}".strip(), limit=PAGES)
            except SearchUnavailable as exc:
                logger.info("Vérification des dates impossible : %s", exc)
                return []
            texts = [text for _, _, text in pages]
            doubts += doubtful_years(years(f"{item.label} {item.statement}"), texts)
        unique = list({d.read: d for d in doubts}.values())
        found = review_items(unique, [(p.index, p.text) for p in ocr.pages])
        if found:
            logger.info("Dates à faire vérifier : %d", len(found))
        return found

    return check
