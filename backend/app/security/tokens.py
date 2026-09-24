"""Jetons : accès parent (JWT signé), jetons opaques (appareil, renouvellement), codes de liaison."""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

import jwt

ALGORITHM = "HS256"
DEVICE_PREFIX = "ldf_d_"
REFRESH_PREFIX = "ldf_r_"
RESET_PREFIX = "ldf_p_"
VERIFY_PREFIX = "ldf_v_"


def sha256(value: str) -> bytes:
    return hashlib.sha256(value.encode()).digest()


@dataclass(frozen=True)
class OpaqueToken:
    value: str  # remis au client, jamais stocké
    hash: bytes  # stocké en base


def opaque_token(prefix: str, nbytes: int = 32) -> OpaqueToken:
    value = prefix + secrets.token_urlsafe(nbytes)
    return OpaqueToken(value, sha256(value))


def link_code() -> str:
    """Code à 6 chiffres, uniforme (000000 à 999999)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def create_access_token(parent_id: uuid.UUID, secret: str, now: datetime, lifetime: timedelta) -> str:
    claims = {"sub": str(parent_id), "typ": "parent", "iat": now, "exp": now + lifetime}
    return jwt.encode(claims, secret, algorithm=ALGORITHM)


class InvalidToken(Exception):
    pass


def decode_access_token(token: str, secret: str) -> uuid.UUID:
    try:
        claims = jwt.decode(token, secret, algorithms=[ALGORITHM], options={"require": ["exp", "sub"]})
    except jwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc
    if claims.get("typ") != "parent":
        raise InvalidToken("type de jeton inattendu")
    try:
        return uuid.UUID(claims["sub"])
    except ValueError as exc:
        raise InvalidToken("sujet invalide") from exc


def looks_like_jwt(token: str) -> bool:
    return token.count(".") == 2
