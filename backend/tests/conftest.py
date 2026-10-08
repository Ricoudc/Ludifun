"""Les tests tournent sur un vrai PostgreSQL (base dédiée `ludifun_test`).

Local : `docker compose up -d db` depuis la racine du dépôt.
L'URL peut être changée avec LUDIFUN_TEST_DATABASE_URL.
"""

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.ai.ocr.vision_llm import VisionLLMOcr
from app.ai.providers.fake import FakeProvider
from app.api.deps import AiProviders
from app.config import Settings
from app.db.base import Base, create_engine
from app.main import create_app
from app.services.email import MemoryEmailSender

TEST_DATABASE_URL = os.environ.get(
    "LUDIFUN_TEST_DATABASE_URL", "postgresql+asyncpg://ludifun:ludifun@localhost:5432/ludifun_test"
)
BACKEND_DIR = Path(__file__).resolve().parents[1]


def alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["database_url"] = TEST_DATABASE_URL
    return config


async def run_alembic(*args: str) -> None:
    """Alembic lance sa propre boucle asyncio : on l'exécute dans un thread."""
    name, *rest = args
    await asyncio.to_thread(getattr(command, name), alembic_config(), *rest)


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await run_alembic("upgrade", "head")
    yield engine
    await engine.dispose()


async def truncate_all(engine: AsyncEngine) -> None:
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))


@pytest.fixture
async def db(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await truncate_all(engine)


def make_app(
    database_url: str = TEST_DATABASE_URL,
    mailer: MemoryEmailSender | None = None,
    llm: FakeProvider | None = None,
) -> FastAPI:
    llm = llm or FakeProvider()
    return create_app(
        Settings(database_url=database_url, environment="test", resources=False),
        email_sender=mailer,
        ai=AiProviders(VisionLLMOcr(llm), llm),
    )


@pytest.fixture
def fake_llm() -> FakeProvider:
    """IA factice des tests d'API : rejoue la leçon d'histoire de référence."""
    return FakeProvider()


@pytest.fixture
def mailer() -> MemoryEmailSender:
    return MemoryEmailSender()


@pytest.fixture
async def app(
    engine: AsyncEngine, mailer: MemoryEmailSender, fake_llm: FakeProvider
) -> AsyncIterator[FastAPI]:
    app = make_app(mailer=mailer, llm=fake_llm)
    async with app.router.lifespan_context(app):
        yield app
    await truncate_all(engine)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
