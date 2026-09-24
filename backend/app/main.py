import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.exc import SQLAlchemyError

from app.ai.factory import build_providers
from app.api import health, v1, web
from app.api.body_limit import BodySizeLimit
from app.api.deps import AiProviders
from app.api.errors import install_error_handlers
from app.config import Settings, get_settings
from app.db.base import Database
from app.domain.activities.registry import default_registry
from app.security.rate_limit import RateLimiter
from app.services.ai_settings import AiResolver
from app.services.email import EmailSender, build_email_sender
from app.services.lesson_processing import recover_interrupted_lessons


def create_app(
    settings: Settings | None = None,
    email_sender: EmailSender | None = None,
    ai: AiProviders | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.database = Database(settings.database_url)
        app.state.settings = settings
        app.state.rate_limiter = RateLimiter()
        app.state.ai = ai or AiProviders(*build_providers(settings))
        app.state.ai_resolver = AiResolver(settings, (app.state.ai.ocr, app.state.ai.llm))
        app.state.registry = default_registry()
        try:
            await recover_interrupted_lessons(app.state.database)
        except (SQLAlchemyError, OSError):  # base injoignable : /health/ready le signalera
            logging.getLogger("ludifun").exception("Récupération des analyses interrompues impossible")
        app.state.email_sender = email_sender or build_email_sender(settings)
        if settings.environment == "prod" and settings.missing_legal_details():
            logging.getLogger("ludifun").warning(
                "Pages publiques incomplètes (%s) : à renseigner avant la bêta.",
                ", ".join(settings.missing_legal_details()),
            )
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
    # Photos d'une leçon au maximum, plus 1 Mo pour l'enveloppe multipart.
    app.add_middleware(BodySizeLimit, max_bytes=settings.max_pages * settings.max_image_bytes + 2**20)
    app.include_router(health.router)
    app.include_router(v1.router)
    app.include_router(web.router)
    return app


app = create_app()
