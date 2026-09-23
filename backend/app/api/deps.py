import math
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.ai.ports import LLMProvider, OcrProvider
from app.api.errors import ApiError
from app.config import Settings
from app.db.base import Database
from app.db.models import Child, Parent
from app.domain.activities.registry import ActivityRegistry
from app.security.rate_limit import RateLimiter
from app.security.tokens import InvalidToken, decode_access_token, looks_like_jwt
from app.services import accounts
from app.services.email import EmailSender


def get_database(request: Request) -> Database:
    db: Database = request.app.state.database
    return db


async def get_db(database: Annotated[Database, Depends(get_database)]) -> AsyncIterator[AsyncSession]:
    async for session in database.session():
        yield session


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_email_sender(request: Request) -> EmailSender:
    sender: EmailSender = request.app.state.email_sender
    return sender


@dataclass(frozen=True)
class AiProviders:
    ocr: OcrProvider
    llm: LLMProvider


def get_ai(request: Request) -> AiProviders:
    providers: AiProviders = request.app.state.ai
    return providers


def get_registry(request: Request) -> ActivityRegistry:
    registry: ActivityRegistry = request.app.state.registry
    return registry


DbSession = Annotated[AsyncSession, Depends(get_db)]
Ai = Annotated[AiProviders, Depends(get_ai)]
Registry = Annotated[ActivityRegistry, Depends(get_registry)]
AppSettings = Annotated[Settings, Depends(get_settings)]
Mailer = Annotated[EmailSender, Depends(get_email_sender)]


# --------------------------------------------------------------------------- #
# Limitation de débit
# --------------------------------------------------------------------------- #


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "inconnu"


def rate_limit(request: Request, key: str, limit: int, window_s: float, *, record: bool = True) -> None:
    """429 si la limite est atteinte ; `record=False` vérifie sans compter d'essai."""
    limiter: RateLimiter = request.app.state.rate_limiter
    wait = limiter.hit(key, limit, window_s) if record else limiter.exceeded(key, limit, window_s)
    if wait is not None:
        raise ApiError(
            429,
            "rate_limited",
            "Trop d'essais. Réessaie dans quelques minutes.",
            headers={"Retry-After": str(math.ceil(wait))},
        )


# --------------------------------------------------------------------------- #
# Qui appelle ? Un parent (jeton d'accès) ou l'appareil d'un enfant (jeton d'appareil)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ParentPrincipal:
    parent_id: uuid.UUID


@dataclass(frozen=True)
class DevicePrincipal:
    child_id: uuid.UUID
    device_id: uuid.UUID


Principal = ParentPrincipal | DevicePrincipal

_UNAUTHORIZED = {"WWW-Authenticate": "Bearer"}


async def current_principal(request: Request, db: DbSession, settings: AppSettings) -> Principal:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ApiError(401, "unauthorized", "Authentification requise.", _UNAUTHORIZED)
    if looks_like_jwt(token):
        try:
            parent_id = decode_access_token(token, settings.jwt_secret.get_secret_value())
        except InvalidToken as exc:
            raise ApiError(401, "invalid_token", "Session expirée, reconnectez-vous.", _UNAUTHORIZED) from exc
        if await db.get(Parent, parent_id) is None:
            raise ApiError(401, "invalid_token", "Session expirée, reconnectez-vous.", _UNAUTHORIZED)
        return ParentPrincipal(parent_id)
    device = await accounts.authenticate_device(db, token, clock.now())
    if device is None:
        raise ApiError(401, "invalid_token", "Cet appareil n'est plus lié.", _UNAUTHORIZED)
    await db.commit()  # dernière utilisation de l'appareil
    return DevicePrincipal(device.child_id, device.id)


async def require_parent(principal: Annotated[Principal, Depends(current_principal)]) -> ParentPrincipal:
    if not isinstance(principal, ParentPrincipal):
        raise ApiError(403, "forbidden", "Réservé à l'espace parent.")
    return principal


async def child_scope(
    principal: Annotated[Principal, Depends(current_principal)],
    db: DbSession,
    child_id: Annotated[uuid.UUID | None, Query(description="Enfant concerné (appel par un parent)")] = None,
) -> Child:
    """L'enfant dont on consulte les données : celui de l'appareil, ou un enfant de la famille du parent."""
    child: Child | None
    if isinstance(principal, DevicePrincipal):
        if child_id is not None and child_id != principal.child_id:
            raise ApiError(404, "child_not_found", "Enfant introuvable.")
        child = await db.get(Child, principal.child_id)
    else:
        if child_id is None:
            raise ApiError(422, "child_id_required", "Préciser l'enfant (child_id).")
        child = await accounts.child_of_parent(db, principal.parent_id, child_id)
    if child is None:
        raise ApiError(404, "child_not_found", "Enfant introuvable.")
    return child


CurrentParent = Annotated[ParentPrincipal, Depends(require_parent)]
ChildInScope = Annotated[Child, Depends(child_scope)]
