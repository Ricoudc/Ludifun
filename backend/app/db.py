from collections.abc import Iterator

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

_settings = get_settings()
if _settings.database_url.startswith("sqlite"):
    # Base en mémoire (tests) : une seule connexion partagée, sinon chaque connexion serait vide.
    _in_memory = _settings.database_url in ("sqlite://", "sqlite:///:memory:")
    engine = create_engine(
        _settings.database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool if _in_memory else None,
    )
else:
    engine = create_engine(_settings.database_url)


def init_db() -> None:
    from app import models  # noqa: F401  (enregistre les tables)

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
