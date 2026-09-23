import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health, v1
from app.api.errors import install_error_handlers
from app.config import Settings, get_settings
from app.db.base import Database


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.database = Database(settings.database_url)
        yield
        await app.state.database.dispose()

    app = FastAPI(
        title="Ludifun API",
        version="0.1.0",
        description="Photo d'une leçon → notions → séance de révision adaptée.",
        lifespan=lifespan,
        # La documentation interactive n'est pas exposée en production.
        docs_url=None if settings.environment == "prod" else "/docs",
        redoc_url=None,
        openapi_url=None if settings.environment == "prod" else "/openapi.json",
    )
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(v1.router)
    return app


app = create_app()
