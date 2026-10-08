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

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import AiChoice, AiConfigError, build_providers
from app.ai.fallback import FallbackLLM
from app.ai.ocr.vision_llm import VisionLLMOcr
from app.ai.ports import LLMProvider, OcrProvider
from app.config import DEV_JWT_SECRET, AiProviderName, Settings
from app.db.models import Child, FamilyAiProvider, FamilyAiSettings, FamilyMember

logger = logging.getLogger("ludifun.ai")

Builder = Callable[[Settings, AiChoice], tuple[OcrProvider, LLMProvider]]


def _secret(settings: Settings) -> str:
    return (settings.secrets_key or settings.jwt_secret).get_secret_value()


def _key(secret: str) -> Fernet:
    digest = hashlib.sha256(b"ludifun/family-ai-keys:" + secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _fernet(settings: Settings) -> MultiFernet:
    """Chiffre avec le secret du serveur. Hors production, relit aussi les clés chiffrées avec
    le secret de développement par défaut (installations d'avant l'audit de septembre 2026)."""
    secret = _secret(settings)
    keys = [_key(secret)]
    if settings.environment != "prod" and secret != DEV_JWT_SECRET:
        keys.append(_key(DEV_JWT_SECRET))
    return MultiFernet(keys)


def encrypt(settings: Settings, value: str) -> bytes:
    return _fernet(settings).encrypt(value.encode())


async def reencrypt_keys(db: AsyncSession, settings: Settings) -> int:
    """Au démarrage : les clés encore chiffrées avec l'ancien secret le sont avec le nouveau.
    Renvoie leur nombre ; une clé illisible reste telle quelle (à saisir de nouveau)."""
    fernet, current = _fernet(settings), _key(_secret(settings))
    count = 0
    rows = await db.scalars(select(FamilyAiProvider).where(FamilyAiProvider.api_key_encrypted.is_not(None)))
    for row in rows:
        token = row.api_key_encrypted
        assert token is not None
        try:
            current.decrypt(token)
            continue
        except InvalidToken:
            pass
        try:
            row.api_key_encrypted = fernet.rotate(token)
            count += 1
        except InvalidToken:
            continue
    await db.commit()
    return count


def decrypt(settings: Settings, token: bytes) -> str | None:
    """`None` si la clé ne se déchiffre plus (secret du serveur changé) : à saisir de nouveau."""
    try:
        return _fernet(settings).decrypt(token).decode()
    except InvalidToken:
        logger.warning(
            "Clé d'IA d'une famille illisible : le secret du serveur a changé (Ludifun lancé depuis un "
            "autre dossier ?). Le parent doit la coller de nouveau (Mon compte → Intelligence artificielle)."
        )
        return None


def key_lost(settings: Settings, token: bytes | None) -> bool:
    """Vrai si une clé est enregistrée mais ne se déchiffre plus (secret du serveur changé :
    Ludifun réinstallé dans un autre dossier, par exemple)."""
    if not token:
        return False
    try:
        _fernet(settings).decrypt(token)
    except InvalidToken:
        return True
    return False


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
    fallback: bool | None = None,
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
        active = FamilyAiSettings(
            family_id=family_id, provider=choice.provider, updated_at=now, fallback=False
        )
        db.add(active)
    else:
        active.provider, active.updated_at = choice.provider, now
    if fallback is not None:
        active.fallback = fallback
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
        """L'IA active de la famille ; si le parent l'a permis (§147), ses autres IA déjà réglées
        prennent le relais quand elle ne répond pas. Jamais l'IA du serveur : la famille a choisi
        où partent les photos."""
        active = await load(db, child.family_id)
        if active is None:
            return self.default
        rows = await load_providers(db, child.family_id)
        row = rows.get(active.provider)
        # IA active sans réglage : ses valeurs par défaut.
        primary = self.for_choice(choice_of(row, self.settings) if row else AiChoice(active.provider))  # type: ignore[arg-type]
        if not active.fallback:
            return primary
        chain = [primary[1]]
        for name, other in rows.items():
            if name == active.provider:
                continue
            try:
                chain.append(self.for_choice(choice_of(other, self.settings))[1])
            except AiConfigError:
                continue  # réglage devenu invalide (clé du serveur retirée…) : ignoré
        if len(chain) == 1:
            return primary
        llm = FallbackLLM(chain)
        return VisionLLMOcr(llm), llm
