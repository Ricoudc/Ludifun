"""L'IA de chaque famille, choisie dans l'espace parent (sans choix : le réglage du serveur).

La clé d'API est chiffrée en base (Fernet, clé dérivée de `LUDIFUN_SECRETS_KEY` ou, à défaut,
de `LUDIFUN_JWT_SECRET`) et n'est jamais renvoyée : l'application n'en voit que la fin.
"""

import base64
import hashlib
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import AiChoice, build_providers
from app.ai.ports import LLMProvider, OcrProvider
from app.config import AiProviderName, Settings
from app.db.models import Child, FamilyAiProvider, FamilyAiSettings, FamilyMember

logger = logging.getLogger("ludifun.ai")

Builder = Callable[[Settings, AiChoice], tuple[OcrProvider, LLMProvider]]


def _fernet(settings: Settings) -> Fernet:
    secret = (settings.secrets_key or settings.jwt_secret).get_secret_value()
    digest = hashlib.sha256(b"ludifun/family-ai-keys:" + secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(settings: Settings, value: str) -> bytes:
    return _fernet(settings).encrypt(value.encode())


def decrypt(settings: Settings, token: bytes) -> str | None:
    """`None` si la clé ne se déchiffre plus (secret du serveur changé) : à saisir de nouveau."""
    try:
        return _fernet(settings).decrypt(token).decode()
    except InvalidToken:
        logger.warning("Clé d'IA d'une famille illisible : le secret du serveur a changé.")
        return None


def hint(key: str) -> str:
    return f"…{key[-4:]}" if len(key) >= 8 else "…"


async def family_of_parent(db: AsyncSession, parent_id: uuid.UUID) -> uuid.UUID | None:
    rows = await db.execute(
        select(FamilyMember.family_id, FamilyMember.role).where(FamilyMember.parent_id == parent_id)
    )
    families = sorted(rows.all(), key=lambda row: row.role != "owner")
    return families[0].family_id if families else None


async def load(db: AsyncSession, family_id: uuid.UUID) -> FamilyAiSettings | None:
    """L'IA active de la famille ; `None` : celle du serveur."""
    return await db.get(FamilyAiSettings, family_id)


async def load_providers(db: AsyncSession, family_id: uuid.UUID) -> dict[str, FamilyAiProvider]:
    """Les IA déjà réglées par la famille (clé, modèle, adresse), par nom."""
    rows = await db.scalars(select(FamilyAiProvider).where(FamilyAiProvider.family_id == family_id))
    return {row.provider: row for row in rows}


def choice_of(row: FamilyAiProvider, settings: Settings) -> AiChoice:
    key = decrypt(settings, row.api_key_encrypted) if row.api_key_encrypted else None
    provider: AiProviderName = row.provider  # type: ignore[assignment]  # contrainte en base
    return AiChoice(provider, row.model, row.base_url, key)


async def save(
    db: AsyncSession,
    family_id: uuid.UUID,
    settings: Settings,
    choice: AiChoice,
    now: datetime,
    keep_key: bool,
) -> None:
    """Enregistre le réglage de cette IA et la rend active. `keep_key` : garder sa clé déjà
    enregistrée. Les réglages des autres IA restent, pour y revenir sans tout ressaisir."""
    row = await db.get(FamilyAiProvider, (family_id, choice.provider))
    if row is None:
        row = FamilyAiProvider(family_id=family_id, provider=choice.provider, updated_at=now)
        db.add(row)
    row.model, row.base_url, row.updated_at = choice.model, choice.base_url, now
    if not keep_key:
        row.api_key_encrypted = encrypt(settings, choice.api_key) if choice.api_key else None
        row.key_hint = hint(choice.api_key) if choice.api_key else None
    active = await load(db, family_id)
    if active is None:
        db.add(FamilyAiSettings(family_id=family_id, provider=choice.provider, updated_at=now))
    else:
        active.provider, active.updated_at = choice.provider, now
    await db.flush()


async def forget(db: AsyncSession, family_id: uuid.UUID, provider: str) -> bool:
    """Oublie le réglage (et la clé) d'une IA ; si c'était l'IA active, la famille revient à
    celle du serveur. Faux si rien n'était enregistré."""
    row = await db.get(FamilyAiProvider, (family_id, provider))
    active = await load(db, family_id)
    if active is not None and active.provider == provider:
        await db.delete(active)
    if row is None:
        return False
    await db.delete(row)
    await db.flush()
    return True


@dataclass
class AiResolver:
    """IA à utiliser pour un enfant : celle de sa famille, sinon celle du serveur. Les
    fournisseurs construits sont gardés (un client HTTP par réglage)."""

    settings: Settings
    default: tuple[OcrProvider, LLMProvider]
    builder: Builder = build_providers

    def __post_init__(self) -> None:
        self._cache: dict[tuple[str, ...], tuple[OcrProvider, LLMProvider]] = {}

    def for_choice(self, choice: AiChoice) -> tuple[OcrProvider, LLMProvider]:
        fingerprint = hashlib.sha256((choice.api_key or "").encode()).hexdigest()
        cache_key = (choice.provider, choice.model or "", choice.base_url or "", fingerprint)
        if cache_key not in self._cache:
            self._cache[cache_key] = self.builder(self.settings, choice)
        return self._cache[cache_key]

    def forget(self) -> None:
        self._cache.clear()

    async def for_child(self, db: AsyncSession, child: Child) -> tuple[OcrProvider, LLMProvider]:
        active = await load(db, child.family_id)
        if active is None:
            return self.default
        row = await db.get(FamilyAiProvider, (child.family_id, active.provider))
        if row is None:  # IA active sans réglage : ses valeurs par défaut
            return self.for_choice(AiChoice(active.provider))  # type: ignore[arg-type]
        return self.for_choice(choice_of(row, self.settings))
