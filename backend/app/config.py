from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration lue depuis les variables d'environnement (préfixe LUDIFUN_)."""

    model_config = SettingsConfigDict(env_prefix="LUDIFUN_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./ludifun.db"

    # "anthropic" : appels réels à Claude (nécessite ANTHROPIC_API_KEY).
    # "fake" : moteur hors-ligne déterministe, pour le développement et les tests.
    llm_provider: str = "fake"
    llm_model: str = "claude-opus-5"

    # Taille maximale d'une photo de leçon, en octets.
    max_image_bytes: int = 10 * 1024 * 1024
    max_images_per_lesson: int = 6

    # Nombre de questions générées par notion lors de l'analyse.
    questions_per_notion: int = 4


@lru_cache
def get_settings() -> Settings:
    return Settings()
