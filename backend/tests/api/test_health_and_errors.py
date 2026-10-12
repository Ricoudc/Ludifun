from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from sqlalchemy.exc import OperationalError

from app.api.errors import UNEXPECTED_MESSAGE, ApiError, ErrorCategory, category_of
from tests.conftest import make_app


async def test_liveness(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_readiness_reports_migrated_schema(client: AsyncClient) -> None:
    r = await client.get("/health/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "schema": "0030", "ai": "fake"}


async def test_readiness_fails_cleanly_without_database() -> None:
    app = make_app("postgresql+asyncpg://ludifun:ludifun@127.0.0.1:1/nope")
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        r = await client.get("/health/ready")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "database_unavailable"


async def test_unknown_route_uses_error_format(client: AsyncClient) -> None:
    r = await client.get("/v1/nothing-here")
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "not_found", "category": "USER_ERROR", "message": "Not Found"}}


class _Body(BaseModel):
    grade: str


async def test_business_and_validation_errors_use_error_format(app: FastAPI, client: AsyncClient) -> None:
    @app.post("/_test/lessons")
    async def _route(body: _Body) -> None:
        raise ApiError(422, "lesson_unreadable", "Je n'arrive pas à lire ta photo.")

    r = await client.post("/_test/lessons", json={"grade": "CM1"})
    assert r.status_code == 422
    assert r.json() == {
        "error": {
            "code": "lesson_unreadable",
            "category": "VALIDATION_ERROR",
            "message": "Je n'arrive pas à lire ta photo.",
        }
    }

    r = await client.post("/_test/lessons", json={})
    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "invalid_request" and error["category"] == "VALIDATION_ERROR"
    assert error["details"][0]["loc"] == ["body", "grade"]


async def test_every_error_has_a_category_from_the_specification(client: AsyncClient) -> None:
    """§135 : USER_ERROR, VALIDATION_ERROR, AUTH_ERROR, AI_ERROR, DATABASE_ERROR, RATE_LIMIT…"""
    assert category_of(401, "invalid_token") is ErrorCategory.AUTH_ERROR
    assert category_of(403, "parent_only") is ErrorCategory.AUTH_ERROR
    assert category_of(409, "session_closed") is ErrorCategory.USER_ERROR
    assert category_of(413, "image_too_large") is ErrorCategory.VALIDATION_ERROR
    assert category_of(429, "rate_limited") is ErrorCategory.RATE_LIMIT
    assert category_of(503, "ai_budget_exhausted") is ErrorCategory.AI_ERROR
    assert category_of(503, "database_unavailable") is ErrorCategory.DATABASE_ERROR
    assert category_of(504, "gateway_timeout") is ErrorCategory.TIMEOUT
    assert category_of(500, "internal_error") is ErrorCategory.UNKNOWN_ERROR
    r = await client.get("/v1/me")
    assert r.status_code == 401 and r.json()["error"]["category"] == "AUTH_ERROR"


async def test_an_unexpected_error_is_never_raw(app: FastAPI, client: AsyncClient) -> None:
    """Un bug ou une base injoignable : le format habituel, un message compréhensible."""

    @app.get("/_test/bug")
    async def _bug() -> None:
        raise RuntimeError("détail technique à ne pas montrer")

    @app.get("/_test/database")
    async def _database() -> None:
        raise OperationalError("SELECT 1", {}, ConnectionRefusedError("refusé"))

    r = await client.get("/_test/bug")
    assert r.status_code == 500
    assert r.json() == {
        "error": {"code": "internal_error", "category": "UNKNOWN_ERROR", "message": UNEXPECTED_MESSAGE}
    }
    assert "technique" not in r.text
    r = await client.get("/_test/database")
    assert r.status_code == 503 and r.json()["error"]["category"] == "DATABASE_ERROR"
