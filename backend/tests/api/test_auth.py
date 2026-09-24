from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import AsyncClient

from app.config import DEV_JWT_SECRET, Settings
from app.services.email import MemoryEmailSender
from tests.api.helpers import PASSWORD, auth, register


async def test_register_returns_a_session(client: AsyncClient) -> None:
    tokens = await register(client, "Parent@Example.fr ")
    assert tokens["token_type"] == "bearer" and tokens["expires_in"] == 900
    assert tokens["parent"]["email"] == "parent@example.fr"  # normalisé
    r = await client.get("/v1/parent", headers=auth(tokens["access_token"]))
    assert r.json()["email"] == "parent@example.fr"


@pytest.mark.parametrize(
    "body, field",
    [
        ({"email": "pas-un-email", "password": PASSWORD, "accepted_privacy_policy": True}, "email"),
        ({"email": "a@example.fr", "password": "court", "accepted_privacy_policy": True}, "password"),
        (
            {"email": "a@example.fr", "password": PASSWORD, "accepted_privacy_policy": False},
            "accepted_privacy_policy",
        ),
        ({"email": "a@example.fr", "password": PASSWORD}, "accepted_privacy_policy"),
    ],
)
async def test_register_validation(client: AsyncClient, body: dict[str, object], field: str) -> None:
    r = await client.post("/v1/auth/register", json=body)
    assert r.status_code == 422
    assert r.json()["error"]["details"][0]["loc"][-1] == field


async def test_email_is_unique_case_insensitively(client: AsyncClient) -> None:
    await register(client, "parent@example.fr")
    r = await client.post(
        "/v1/auth/register",
        json={"email": "PARENT@example.fr", "password": PASSWORD, "accepted_privacy_policy": True},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "email_taken"


async def test_login(client: AsyncClient) -> None:
    await register(client)
    ok = await client.post("/v1/auth/login", json={"email": "parent@example.fr", "password": PASSWORD})
    assert ok.status_code == 200 and ok.json()["access_token"]
    for email, password in (("parent@example.fr", "mauvais mot de passe"), ("inconnu@example.fr", PASSWORD)):
        r = await client.post("/v1/auth/login", json={"email": email, "password": password})
        # Même réponse que l'e-mail existe ou non.
        assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"


async def test_login_is_rate_limited(client: AsyncClient) -> None:
    await register(client)
    bad = {"email": "parent@example.fr", "password": "mauvais mot de passe"}
    codes = [(await client.post("/v1/auth/login", json=bad)).status_code for _ in range(6)]
    assert codes == [401] * 5 + [429]
    r = await client.post("/v1/auth/login", json={"email": "parent@example.fr", "password": PASSWORD})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0


async def test_refresh_rotation_and_reuse_detection(client: AsyncClient) -> None:
    first = await register(client)
    second = (await client.post("/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})).json()
    assert second["refresh_token"] != first["refresh_token"]
    third = await client.post("/v1/auth/refresh", json={"refresh_token": second["refresh_token"]})
    assert third.status_code == 200

    # Réutiliser un jeton déjà échangé = vol probable : toute la chaîne est révoquée.
    stolen = await client.post("/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert stolen.status_code == 401
    latest = await client.post("/v1/auth/refresh", json={"refresh_token": third.json()["refresh_token"]})
    assert latest.status_code == 401


async def test_logout_revokes_the_refresh_token(client: AsyncClient) -> None:
    tokens = await register(client)
    assert (
        await client.post("/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    ).status_code == 204
    r = await client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 401


@pytest.mark.parametrize("problem", ["expired", "bad_signature", "wrong_type", "garbage"])
async def test_invalid_access_tokens(client: AsyncClient, problem: str) -> None:
    tokens = await register(client)
    parent_id = tokens["parent"]["id"]
    now = datetime.now(UTC)
    claims = {"sub": parent_id, "typ": "parent", "iat": now, "exp": now + timedelta(minutes=5)}
    token = {
        "expired": jwt.encode(claims | {"exp": now - timedelta(seconds=1)}, DEV_JWT_SECRET, "HS256"),
        "bad_signature": jwt.encode(claims, "un-autre-secret-assez-long-pour-hs256-00000", "HS256"),
        "wrong_type": jwt.encode(claims | {"typ": "child"}, DEV_JWT_SECRET, "HS256"),
        "garbage": "a.b.c",
    }[problem]
    r = await client.get("/v1/parent", headers=auth(token))
    assert r.status_code == 401 and r.headers["WWW-Authenticate"] == "Bearer"


async def test_password_reset(client: AsyncClient, mailer: MemoryEmailSender) -> None:
    old = await register(client)
    mailer.sent.clear()  # « Confirmez votre adresse »
    unknown = await client.post("/v1/auth/password-reset", json={"email": "inconnu@example.fr"})
    known = await client.post("/v1/auth/password-reset", json={"email": "parent@example.fr"})
    assert unknown.status_code == known.status_code == 202 and unknown.json() == known.json()
    assert [m.to for m in mailer.sent] == ["parent@example.fr"]
    token = mailer.sent[0].body.split("ludifun://app/parent/nouveau-mot-de-passe?jeton=")[1].split()[0]

    new_password = "un tout nouveau mot de passe"
    r = await client.post(
        "/v1/auth/password-reset/confirm", json={"token": token, "new_password": new_password}
    )
    assert r.status_code == 204
    again = await client.post(
        "/v1/auth/password-reset/confirm", json={"token": token, "new_password": new_password}
    )
    assert again.status_code == 400  # usage unique

    login = await client.post("/v1/auth/login", json={"email": "parent@example.fr", "password": new_password})
    assert login.status_code == 200
    # Les autres sessions sont déconnectées.
    assert (
        await client.post("/v1/auth/refresh", json={"refresh_token": old["refresh_token"]})
    ).status_code == 401


def test_production_requires_a_real_secret() -> None:
    with pytest.raises(ValueError, match="LUDIFUN_JWT_SECRET"):
        Settings(environment="prod")
    Settings(environment="prod", jwt_secret="un-vrai-secret-de-production-tres-long-0123456789")
