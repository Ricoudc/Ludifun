"""Format d'erreur unique (cahier des charges §11.2, §135) :

{"error": {"code": "lesson_not_found", "category": "USER_ERROR", "message": "…"}}

Chaque erreur a un code métier, une catégorie du §135 (comportement défini côté application) et
un message en français pour l'utilisateur. Une erreur inattendue du serveur ne sort jamais brute
(« 500 Internal Server Error ») : `CatchUnexpected` répond dans ce même format.
"""

import json
import logging
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("ludifun.errors")


class ErrorCategory(StrEnum):
    """Catégories d'erreurs du cahier des charges (§135)."""

    USER_ERROR = "USER_ERROR"  # action impossible dans l'état actuel (introuvable, déjà fait…)
    VALIDATION_ERROR = "VALIDATION_ERROR"  # requête ou donnée refusée
    NETWORK_ERROR = "NETWORK_ERROR"  # côté application seulement : pas de réseau
    AUTH_ERROR = "AUTH_ERROR"  # pas connecté, ou pas le droit
    OCR_ERROR = "OCR_ERROR"  # photo illisible
    AI_ERROR = "AI_ERROR"  # IA indisponible, plafond de coût atteint
    DATABASE_ERROR = "DATABASE_ERROR"  # base de données injoignable
    TIMEOUT = "TIMEOUT"  # trop long
    RATE_LIMIT = "RATE_LIMIT"  # trop de demandes
    UNKNOWN_ERROR = "UNKNOWN_ERROR"  # erreur inattendue


# Codes métier dont la catégorie ne se déduit pas du statut HTTP.
_CODE_CATEGORIES = {
    "ai_budget_exhausted": ErrorCategory.AI_ERROR,
    "images_unavailable": ErrorCategory.AI_ERROR,
    "database_unavailable": ErrorCategory.DATABASE_ERROR,
    "internal_error": ErrorCategory.UNKNOWN_ERROR,
}
_STATUS_CATEGORIES = {
    400: ErrorCategory.VALIDATION_ERROR,
    401: ErrorCategory.AUTH_ERROR,
    403: ErrorCategory.AUTH_ERROR,
    404: ErrorCategory.USER_ERROR,
    405: ErrorCategory.USER_ERROR,
    409: ErrorCategory.USER_ERROR,
    413: ErrorCategory.VALIDATION_ERROR,
    415: ErrorCategory.VALIDATION_ERROR,
    422: ErrorCategory.VALIDATION_ERROR,
    429: ErrorCategory.RATE_LIMIT,
    504: ErrorCategory.TIMEOUT,
}


# Raison d'échec de l'analyse d'une leçon (statut de la leçon, pas une erreur HTTP).
FAILURE_CATEGORIES = {
    "unreadable": ErrorCategory.OCR_ERROR,
    "not_a_lesson": ErrorCategory.USER_ERROR,
    "too_long": ErrorCategory.VALIDATION_ERROR,
    "ai_error": ErrorCategory.AI_ERROR,
}


def category_of(status_code: int, code: str) -> ErrorCategory:
    return _CODE_CATEGORIES.get(code) or _STATUS_CATEGORIES.get(status_code, ErrorCategory.UNKNOWN_ERROR)


# Codes génériques utilisés quand une erreur HTTP est levée sans code métier.
_DEFAULT_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "invalid_request",
    429: "rate_limited",
    503: "service_unavailable",
}


class ApiError(Exception):
    """Erreur métier : `raise ApiError(404, "lesson_not_found", "Leçon introuvable.")`."""

    def __init__(
        self, status_code: int, code: str, message: str, headers: dict[str, str] | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers


def error_body(code: str, message: str, details: Any = None, status_code: int = 500) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": code,
        "category": category_of(status_code, code).value,
        "message": message,
    }
    if details is not None:
        error["details"] = details
    return {"error": error}


async def _api_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return JSONResponse(
        error_body(exc.code, exc.message, status_code=exc.status_code),
        status_code=exc.status_code,
        headers=exc.headers,
    )


async def _http_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _DEFAULT_CODES.get(exc.status_code, "error")
    message = exc.detail if isinstance(exc.detail, str) else code
    return JSONResponse(
        error_body(code, message, status_code=exc.status_code),
        status_code=exc.status_code,
        headers=exc.headers,
    )


async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    details = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
    return JSONResponse(
        error_body("invalid_request", "Requête invalide.", details, status_code=422), status_code=422
    )


UNEXPECTED_MESSAGE = "Petit souci de notre côté : réessaie dans un moment."
DATABASE_MESSAGE = "Le serveur Ludifun ne trouve pas sa base de données : réessaie dans un moment."


class CatchUnexpected:
    """Une erreur inattendue pendant une requête : réponse au format habituel (§135), jamais un
    « 500 Internal Server Error » brut ; le détail technique va dans le journal (sans données
    d'enfant : méthode et chemin seulement)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def watch(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, watch)
        except Exception as exc:
            if started:  # réponse déjà partie (tâche de fond) : rien à remplacer
                raise
            logger.exception("Erreur inattendue : %s %s", scope.get("method"), scope.get("path"))
            if isinstance(exc, OperationalError | ConnectionRefusedError):
                status, body = 503, error_body("database_unavailable", DATABASE_MESSAGE, status_code=503)
            else:
                status, body = 500, error_body("internal_error", UNEXPECTED_MESSAGE, status_code=500)
            payload = json.dumps(body, ensure_ascii=False).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": status,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(payload)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": payload})


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_middleware(CatchUnexpected)
