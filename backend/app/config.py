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
    # Correction des réponses rédigées, pendant la séance : rapide et peu coûteuse.
    ai_evaluation_model: str = "claude-sonnet-5"
    ai_ocr_effort: Effort = "low"
    ai_analysis_effort: Effort = "high"
    ai_material_effort: Effort = "medium"
    ai_evaluation_effort: Effort = "low"
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
    # Confirmation de l'adresse du parent (étape 19) : page web de l'API en production
    # (https://…/verifier-email?jeton=), sinon l'application.
    email_verification_url: str = "ludifun://app/parent/verifier-email?jeton="
    email_verification_days: int = 7

    # E-mails (étape 19) : fournisseur SMTP hébergé dans l'UE ; sans hôte, journal (dev seulement).
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    email_from: str = "Ludifun <bonjour@ludifun.fr>"

    # Conservation (§16.2) : prévenance puis suppression d'un compte inactif.
    inactive_warning_days: int = 335  # environ 11 mois
    inactive_delete_days: int = 365
    inactive_notice_days: int = 30  # délai minimal entre la prévenance et la suppression

    # Pages publiques (confidentialité, suppression du compte) : à renseigner avant la bêta.
    legal_entity: str = "[À COMPLÉTER : nom et adresse de l'éditeur]"
    contact_email: str = "[À COMPLÉTER : adresse de contact]"
    hosting_provider: str = "[À COMPLÉTER : hébergeur]"
    email_provider: str = "[À COMPLÉTER : fournisseur d'e-mails]"
    privacy_updated: str = "24/09/2026"

    family_timezone: str = "Europe/Paris"  # semaines du tableau de bord parent (§11)

    def missing_legal_details(self) -> list[str]:
        """Réglages des pages publiques encore à compléter (LUDIFUN_LEGAL_ENTITY…)."""
        fields = ("legal_entity", "contact_email", "hosting_provider", "email_provider")
        return [
            f"LUDIFUN_{name.upper()}" for name in fields if getattr(self, name).startswith("[À COMPLÉTER")
        ]

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
