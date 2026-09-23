from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration lue dans l'environnement (préfixe LUDIFUN_) ou un fichier .env."""

    model_config = SettingsConfigDict(env_prefix="LUDIFUN_", env_file=".env", extra="ignore")

    environment: Literal["dev", "test", "prod"] = "dev"
    database_url: str = "postgresql+asyncpg://ludifun:ludifun@localhost:5432/ludifun"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
