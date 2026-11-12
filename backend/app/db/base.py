from collections.abc import AsyncIterator

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# Noms de contraintes stables : indispensable pour qu'Alembic produise des migrations prévisibles.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


class Database:
    """Moteur + fabrique de sessions, créés au démarrage de l'application."""

    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url)
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessionmaker() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()
