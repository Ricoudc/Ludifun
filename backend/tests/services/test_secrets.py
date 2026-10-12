"""Secrets propres à chaque installation (audit de septembre 2026) : un .env sans secret ne
casse rien, et les clés d'IA chiffrées avec l'ancien secret public restent lisibles puis sont
rechiffrées avec le nouveau au démarrage."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import DEV_JWT_SECRET, Settings
from app.db.models import Family, FamilyAiProvider
from app.services.ai_settings import decrypt, encrypt, reencrypt_keys

OLD = Settings(environment="dev")
NEW = Settings(environment="dev", jwt_secret="un-secret-tire-au-hasard-pour-ce-pc-0123456789")


def test_empty_values_from_docker_compose_mean_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LUDIFUN_JWT_SECRET", "")
    monkeypatch.setenv("LUDIFUN_SECRETS_KEY", "")
    settings = Settings()
    assert settings.jwt_secret.get_secret_value() == DEV_JWT_SECRET and settings.uses_dev_secret
    assert settings.secrets_key is None
    with pytest.raises(ValueError, match="LUDIFUN_JWT_SECRET"):
        Settings(environment="prod", jwt_secret="")


def test_keys_encrypted_with_the_old_public_secret_stay_readable() -> None:
    old_token = encrypt(OLD, "sk-ant-secret-1234")
    assert decrypt(NEW, old_token) == "sk-ant-secret-1234"
    assert decrypt(NEW, encrypt(NEW, "gsk_cle")) == "gsk_cle"
    assert decrypt(OLD, encrypt(NEW, "gsk_cle")) is None  # le nouveau secret protège vraiment
    # En production, jamais de repli sur le secret public.
    prod = Settings(environment="prod", jwt_secret=NEW.jwt_secret)
    assert decrypt(prod, old_token) is None


async def test_reencrypt_at_startup(db: AsyncSession) -> None:
    family = Family(id=uuid.uuid4())
    db.add(family)
    await db.flush()
    keys = {"claude": encrypt(OLD, "sk-ant-1"), "gemini": encrypt(NEW, "g-2"), "ollama": None}
    db.add_all(
        FamilyAiProvider(
            family_id=family.id, provider=provider, api_key_encrypted=key, updated_at=datetime.now(UTC)
        )
        for provider, key in keys.items()
    )
    await db.commit()
    assert await reencrypt_keys(db, NEW) == 1
    assert await reencrypt_keys(db, NEW) == 0
    rows = {r.provider: r.api_key_encrypted for r in await db.scalars(select(FamilyAiProvider))}
    assert decrypt(NEW.model_copy(update={"environment": "prod"}), rows["claude"] or b"") == "sk-ant-1"
    assert decrypt(NEW, rows["gemini"] or b"") == "g-2"
