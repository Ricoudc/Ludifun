"""Page `/suivi` : les appels à l'IA en direct, pour comprendre une analyse lente ou ratée.

Ouverte hors production (réglage `LUDIFUN_MONITORING`) ; aucune donnée personnelle (voir
`app.services.monitoring`). La page se rafraîchit seule toutes les 3 secondes.
"""

from importlib import resources
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from app import clock
from app.api.deps import AppSettings, DbSession, get_ai_resolver
from app.api.errors import ApiError
from app.config import Settings
from app.services import monitoring
from app.services.live_calls import LIVE

router = APIRouter(tags=["suivi"], include_in_schema=False)

HEADERS = {
    "Content-Security-Policy": "default-src 'none'; script-src 'self'; connect-src 'self'; "
    "style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def _allowed(settings: Settings) -> None:
    if not settings.monitoring_enabled:
        raise ApiError(404, "not_found", "Page introuvable.")


def _asset(name: str) -> str:
    return resources.files("app.web").joinpath(name).read_text(encoding="utf-8")


def server_ai(request: Request) -> str:
    llm = get_ai_resolver(request).default[1]
    try:
        return f"{llm.name} ({llm.model_for('ocr')})"
    except (KeyError, AttributeError):
        return llm.name


async def report(request: Request, db: DbSession) -> dict[str, Any]:
    return await monitoring.snapshot(db, clock.now(), server_ai(request), LIVE)


@router.get("/suivi")
async def page(settings: AppSettings) -> HTMLResponse:
    _allowed(settings)
    return HTMLResponse(_asset("suivi.html"), headers=HEADERS)


@router.get("/suivi/suivi.js")
async def script(settings: AppSettings) -> Response:
    _allowed(settings)
    return Response(_asset("suivi.js"), media_type="text/javascript", headers=HEADERS)


@router.get("/suivi/donnees")
async def data(request: Request, db: DbSession, settings: AppSettings) -> dict[str, Any]:
    _allowed(settings)
    return await report(request, db)


@router.get("/suivi/rapport.txt")
async def text(request: Request, db: DbSession, settings: AppSettings) -> Response:
    """Le rapport en texte simple (Ludifun.bat, choix 10), à copier dans une conversation."""
    _allowed(settings)
    content = monitoring.as_text(await report(request, db))
    return Response(content, media_type="text/plain; charset=utf-8", headers=HEADERS)
