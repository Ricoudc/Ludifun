import os

os.environ["LUDIFUN_DATABASE_URL"] = "sqlite://"
os.environ["LUDIFUN_LLM_PROVIDER"] = "fake"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from app.db import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    init_db()
    with TestClient(app) as c:
        yield c
    SQLModel.metadata.drop_all(engine)


@pytest.fixture
def child(client):
    r = client.post("/children", json={"display_name": "Emma", "grade": "CM1"})
    assert r.status_code == 201
    return r.json()


@pytest.fixture
def lesson(client, child):
    r = client.post("/lessons", data={"child_id": child["id"]}, files=[("images", ("page.jpg", b"fake", "image/jpeg"))])
    assert r.status_code == 201, r.text
    return r.json()
