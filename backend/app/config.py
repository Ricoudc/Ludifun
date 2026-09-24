from functools import lru_cache
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Effort = Literal["low", "medium", "high", "xhigh", "max"]
DEV_JWT_SECRET = "dev-uniquement-a-remplacer-en-production-0123456789"


class Settings(BaseSettings):
    """Configuration lue dans l'environnement (préfixe LUDIFUN_) ou un fichier .env."""

    model_config = SettingsConfigDict(env_prefix="LUDIFUN_", env_file=".env", extra="ignore")

    environment: Literal["dev", "test", "prod"] = "dev"
    database_url: str = "postgresql+asyncpg://ludifun:ludifun@localhost:5432/ludifun"
    log_level: str = "INFO"

    # IA (cahier des charges §5.4) : fournisseur, puis modèle et effort par étape.
    ai_provider: Literal["claude", "fake"] = "claude"
    ai_ocr_model: str = "claude-opus-5"
    ai_analysis_model: str = "claude-opus-5"
    ai_material_model: str = "claude-opus-5"
    ai_ocr_effort: Effort = "low"
    ai_analysis_effort: Effort = "high"
    ai_material_effort: Effort = "medium"
    max_lesson_chars: int = 20000
    # Plafond de dépense IA par jour (UTC), tous comptes confondus ; vide = pas de plafond.
    ai_daily_budget_usd: float | None = 50.0
    max_pages: int = 6
    max_image_bytes: int = 8 * 1024 * 1024
    lessons_per_day: int = 20  # par enfant

    # Comptes (§16.1)
    jwt_secret: SecretStr = SecretStr(DEV_JWT_SECRET)
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    link_code_minutes: int = 10
    password_reset_minutes: int = 60
    # Lien ouvert par l'application (écran « nouveau mot de passe ») ; le jeton est ajouté à la fin.
    password_reset_url: str = "ludifun://app/parent/nouveau-mot-de-passe?jeton="
    family_timezone: str = "Europe/Paris"  # semaines du tableau de bord parent (§11)

    @field_validator("family_timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"fuseau horaire inconnu : {value}") from exc
        return value

    @model_validator(mode="after")
    def _secret_in_production(self) -> "Settings":
        if self.environment == "prod" and self.jwt_secret.get_secret_value() == DEV_JWT_SECRET:
            raise ValueError("LUDIFUN_JWT_SECRET doit être défini en production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
