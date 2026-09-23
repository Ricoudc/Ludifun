from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import DbSession
from app.api.errors import ApiError

router = APIRouter(tags=["système"])


@router.get("/health")
async def liveness() -> dict[str, str]:
    """Le processus répond (utilisé par l'orchestrateur pour redémarrer l'API)."""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(db: DbSession) -> dict[str, str]:
    """L'API est prête à servir : la base est joignable et migrée."""
    try:
        version = (await db.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    except (SQLAlchemyError, OSError) as exc:  # OSError : serveur injoignable
        raise ApiError(503, "database_unavailable", "Base de données indisponible.") from exc
    return {"status": "ok", "schema": version}
