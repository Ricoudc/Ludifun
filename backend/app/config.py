from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Effort = Literal["low", "medium", "high", "xhigh", "max"]


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


@lru_cache
def get_settings() -> Settings:
    return Settings()
