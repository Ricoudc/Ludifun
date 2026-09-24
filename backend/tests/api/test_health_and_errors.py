from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from app.api.errors import ApiError
from tests.conftest import make_app


async def test_liveness(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_readiness_reports_migrated_schema(client: AsyncClient) -> None:
    r = await client.get("/health/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "schema": "0008"}


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
    assert r.json() == {"error": {"code": "not_found", "message": "Not Found"}}


class _Body(BaseModel):
    grade: str


async def test_business_and_validation_errors_use_error_format(app: FastAPI, client: AsyncClient) -> None:
    @app.post("/_test/lessons")
    async def _route(body: _Body) -> None:
        raise ApiError(422, "lesson_unreadable", "Je n'arrive pas à lire ta photo.")

    r = await client.post("/_test/lessons", json={"grade": "CM1"})
    assert r.status_code == 422
    assert r.json() == {"error": {"code": "lesson_unreadable", "message": "Je n'arrive pas à lire ta photo."}}

    r = await client.post("/_test/lessons", json={})
    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "invalid_request"
    assert error["details"][0]["loc"] == ["body", "grade"]
