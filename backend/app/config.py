from functools import lru_cache
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.sources import DEFAULT_SITES

Effort = Literal["low", "medium", "high", "xhigh", "max"]
AiProviderName = Literal[
    "ollama", "claude", "openai", "gemini", "mistral", "groq", "xai", "compatible", "fake"
]
DEV_JWT_SECRET = "dev-uniquement-a-remplacer-en-production-0123456789"


class Settings(BaseSettings):
    """Configuration lue dans l'environnement (préfixe LUDIFUN_) ou un fichier .env."""

    model_config = SettingsConfigDict(env_prefix="LUDIFUN_", env_file=".env", extra="ignore")

    environment: Literal["dev", "test", "prod"] = "dev"
    database_url: str = "postgresql+asyncpg://ludifun:ludifun@localhost:5432/ludifun"
    log_level: str = "INFO"

    # IA (cahier des charges §5.4) : fournisseur, puis modèle et effort par étape. Sans modèle
    # précisé, chaque fournisseur a ses modèles conseillés (app/ai/presets.py).
    ai_provider: AiProviderName = "claude"
    ai_model: str | None = None  # un seul modèle pour toutes les étapes
    ai_ocr_model: str | None = None
    ai_analysis_model: str | None = None
    ai_material_model: str | None = None
    # Correction des réponses rédigées, pendant la séance : rapide et peu coûteuse.
    ai_evaluation_model: str | None = None
    # Fournisseur « compatible » (Azure OpenAI, OpenRouter, Ollama…) : adresse et clé de l'API.
    ai_base_url: str | None = None
    ai_api_key: SecretStr | None = None
    # Ollama : IA locale, gratuite. Dans Docker, http://host.docker.internal:11434 (docker-compose).
    ollama_base_url: str = "http://localhost:11434"
    ollama_num_ctx: int = 8192  # contexte : consignes, leçon, schéma et une notion doivent y tenir
    # Réglage de l'IA par famille (espace parent). Les adresses libres (Ollama, service
    # compatible) font appeler une adresse choisie par le parent : refusées en production sauf
    # si ce réglage vaut true (serveur familial).
    allow_custom_ai_url: bool | None = None
    # Page /suivi (appels à l'IA en direct, sans donnée personnelle) : ouverte hors production,
    # sauf si ce réglage dit le contraire.
    monitoring: bool | None = None
    # Recherche de sources (étape 24) : adresse du moteur SearXNG (docker compose, profil
    # « recherche » : http://recherche:8080) ; vide = désactivée. Sites autorisés, séparés par des
    # virgules (vide = liste par défaut : Vikidia, Lumni, Éduscol, Sésamath, Wikipédia…).
    web_search_url: str | None = None
    # Images des leçons (étape 27) : moteur sur le PC (sdcpp = stable-diffusion.cpp, comfyui),
    # « fake » pour les tests, « none » sans images. Les images attendent la validation du parent.
    image_engine: Literal["none", "fake", "sdcpp", "comfyui"] = "none"
    image_url: str | None = None  # par exemple http://host.docker.internal:7860
    image_model: str | None = None
    media_dir: str = "data/images"  # images générées (jamais de photo d'enfant)
    web_sources: str = ""
    # Chiffrement des clés d'IA des familles ; à défaut, dérivé de LUDIFUN_JWT_SECRET.
    secrets_key: SecretStr | None = None
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

    @property
    def custom_ai_url_allowed(self) -> bool:
        if self.allow_custom_ai_url is not None:
            return self.allow_custom_ai_url
        return self.environment != "prod"

    @property
    def web_sites(self) -> tuple[str, ...]:
        sites = tuple(s.strip().lower() for s in self.web_sources.split(",") if s.strip())
        return sites or DEFAULT_SITES

    @property
    def monitoring_enabled(self) -> bool:
        return self.monitoring if self.monitoring is not None else self.environment != "prod"

    def missing_legal_details(self) -> list[str]:
        """Réglages des pages publiques encore à compléter (LUDIFUN_LEGAL_ENTITY…)."""
        fields = ("legal_entity", "contact_email", "hosting_provider", "email_provider")
        return [
            f"LUDIFUN_{name.upper()}" for name in fields if getattr(self, name).startswith("[À COMPLÉTER")
        ]

    # Docker Compose transmet une chaîne vide pour une variable absente du .env.
    @field_validator("jwt_secret", mode="before")
    @classmethod
    def _default_jwt_secret(cls, value: object) -> object:
        return DEV_JWT_SECRET if isinstance(value, str) and not value.strip() else value

    @field_validator("secrets_key", "web_search_url", mode="before")
    @classmethod
    def _no_empty_secrets_key(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @property
    def uses_dev_secret(self) -> bool:
        """Secret public du dépôt : n'importe qui sur le réseau pourrait se faire passer pour un parent."""
        return self.jwt_secret.get_secret_value() == DEV_JWT_SECRET

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
        if self.environment == "prod" and self.uses_dev_secret:
            raise ValueError("LUDIFUN_JWT_SECRET doit être défini en production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
