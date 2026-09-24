"""Étape 19 : confirmation de l'e-mail du parent, pages publiques et envoi par SMTP."""

import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any, ClassVar

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import EmailVerificationToken
from app.services.email import (
    Email,
    EmailNotSent,
    LogEmailSender,
    MemoryEmailSender,
    SmtpEmailSender,
    build_email_sender,
)
from tests.api.helpers import auth, register

LINK = "ludifun://app/parent/verifier-email?jeton="


def link_token(mailer: MemoryEmailSender, index: int = -1) -> str:
    return mailer.sent[index].body.split(LINK)[1].split()[0]


async def test_registration_sends_a_verification_link(client: AsyncClient, mailer: MemoryEmailSender) -> None:
    parent = await register(client)
    assert parent["parent"]["email_verified"] is False
    assert [(m.to, m.subject) for m in mailer.sent] == [
        ("parent@example.fr", "Ludifun : confirmez votre adresse e-mail")
    ]
    token = link_token(mailer)

    r = await client.post("/v1/auth/verify-email", json={"token": token})
    assert r.status_code == 200 and r.json()["email_verified"] is True
    me = (await client.get("/v1/parent", headers=auth(parent["access_token"]))).json()
    assert me["email_verified"] is True
    # Rouvrir le même lien ne fait pas d'erreur ; un faux lien, si.
    assert (await client.post("/v1/auth/verify-email", json={"token": token})).status_code == 200
    bad = await client.post("/v1/auth/verify-email", json={"token": "ldf_v_faux"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "invalid_verification_token"

    # Plus rien à renvoyer une fois l'adresse confirmée.
    r = await client.post("/v1/parent/verify-email", headers=auth(parent["access_token"]))
    assert r.status_code == 409


async def test_links_expire_and_can_be_resent(
    client: AsyncClient, db: AsyncSession, mailer: MemoryEmailSender
) -> None:
    parent = await register(client)
    first = link_token(mailer)
    link = await db.scalar(select(EmailVerificationToken))
    assert link is not None and abs(link.expires_at - link.created_at - timedelta(days=7)) < timedelta(
        seconds=5
    )
    link.expires_at = datetime.now(UTC) - timedelta(minutes=1)  # 7 jours plus tard
    await db.commit()
    assert (await client.post("/v1/auth/verify-email", json={"token": first})).status_code == 400

    token = parent["access_token"]
    for _ in range(3):
        assert (await client.post("/v1/parent/verify-email", headers=auth(token))).status_code == 202
    assert (await client.post("/v1/parent/verify-email", headers=auth(token))).status_code == 429
    assert len(mailer.sent) == 4
    assert (
        await client.post("/v1/auth/verify-email", json={"token": link_token(mailer, 1)})
    ).status_code == 200


async def test_verification_page_for_any_device(client: AsyncClient, mailer: MemoryEmailSender) -> None:
    await register(client)
    token = link_token(mailer)

    # Le lien de l'e-mail n'agit pas seul : il affiche un bouton (les antivirus ouvrent les liens).
    form = await client.get("/verifier-email", params={"jeton": token})
    assert form.status_code == 200 and f"value='{token}'" in form.text
    assert "default-src 'none'" in form.headers["Content-Security-Policy"]
    hostile = await client.get("/verifier-email", params={"jeton": "'><script>alert(1)</script>"})
    assert "<script>" not in hostile.text

    done = await client.post("/verifier-email", data={"jeton": token})
    assert done.status_code == 200 and "Adresse confirmée" in done.text
    expired = await client.post("/verifier-email", data={"jeton": "ldf_v_faux"})
    assert expired.status_code == 400 and "plus valable" in expired.text


async def test_public_pages(app: FastAPI, client: AsyncClient) -> None:
    app.state.settings = app.state.settings.model_copy(
        update={"legal_entity": "Ludifun SAS, Lyon", "contact_email": "vie-privee@ludifun.fr"}
    )
    policy = await client.get("/confidentialite")
    assert policy.status_code == 200 and "Ludifun SAS, Lyon" in policy.text
    assert "vie-privee@ludifun.fr" in policy.text and "{{" not in policy.text
    assert "[À COMPLÉTER : hébergeur]" in policy.text  # encore à renseigner
    deletion = await client.get("/suppression-compte")
    assert deletion.status_code == 200 and "Supprimer mon compte" in deletion.text
    assert Settings().missing_legal_details() == [
        "LUDIFUN_LEGAL_ENTITY",
        "LUDIFUN_CONTACT_EMAIL",
        "LUDIFUN_HOSTING_PROVIDER",
        "LUDIFUN_EMAIL_PROVIDER",
    ]


class BrokenSender:
    async def send(self, email: Email) -> None:
        raise EmailNotSent


async def test_email_provider_down(app: FastAPI, client: AsyncClient) -> None:
    app.state.email_sender = BrokenSender()
    parent = await register(client)  # le compte est créé quand même
    assert parent["parent"]["email_verified"] is False
    r = await client.post("/v1/parent/verify-email", headers=auth(parent["access_token"]))
    assert r.status_code == 503 and r.json()["error"]["code"] == "email_unavailable"
    r = await client.post("/v1/auth/password-reset", json={"email": "parent@example.fr"})
    assert r.status_code == 503


class FakeSmtp:
    instances: ClassVar[list["FakeSmtp"]] = []
    fail = False

    def __init__(self, host: str, port: int, timeout: float, **kwargs: Any) -> None:
        self.calls: list[Any] = [("connect", host, port, "context" in kwargs)]
        FakeSmtp.instances.append(self)

    def __enter__(self) -> "FakeSmtp":
        return self

    def __exit__(self, *_: object) -> None:
        self.calls.append("quit")

    def starttls(self, context: Any) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        if FakeSmtp.fail:
            raise smtplib.SMTPAuthenticationError(535, b"refuse")
        self.calls.append(("login", user, password))

    def send_message(self, message: EmailMessage) -> None:
        self.calls.append(("send", message["To"], message["From"], message["Subject"], message.get_content()))


async def test_smtp_sender(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSmtp)
    FakeSmtp.instances, FakeSmtp.fail = [], False
    settings = Settings(
        smtp_host="smtp.example.eu",
        smtp_username="ludifun",
        smtp_password="secret",
        email_from="Ludifun <a@b.fr>",
    )
    sender = build_email_sender(settings)
    assert isinstance(sender, SmtpEmailSender)
    await sender.send(Email("parent@example.fr", "Objet", "Bonjour"))
    assert FakeSmtp.instances[0].calls == [
        ("connect", "smtp.example.eu", 587, False),
        "starttls",
        ("login", "ludifun", "secret"),
        ("send", "parent@example.fr", "Ludifun <a@b.fr>", "Objet", "Bonjour\n"),
        "quit",
    ]

    implicit = SmtpEmailSender("smtp.example.eu", 465, None, None, "a@b.fr")
    await implicit.send(Email("parent@example.fr", "Objet", "Bonjour"))
    assert FakeSmtp.instances[1].calls[0] == ("connect", "smtp.example.eu", 465, True)
    assert "starttls" not in FakeSmtp.instances[1].calls

    FakeSmtp.fail = True
    with pytest.raises(EmailNotSent):
        await sender.send(Email("parent@example.fr", "Objet", "Bonjour"))


def test_without_smtp_host_emails_go_to_the_log() -> None:
    dev = build_email_sender(Settings())
    prod = build_email_sender(
        Settings(environment="prod", jwt_secret="un-vrai-secret-de-production-0123456789")
    )
    assert isinstance(dev, LogEmailSender) and dev.include_body
    assert isinstance(prod, LogEmailSender) and not prod.include_body
