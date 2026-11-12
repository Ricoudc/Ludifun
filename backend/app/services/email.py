"""Envoi d'e-mails aux parents : confirmation de l'adresse, mot de passe oublié, prévenance
avant la suppression d'un compte inactif.

Un fournisseur SMTP hébergé dans l'UE (étape 19, `LUDIFUN_SMTP_*`) ; sans lui, les messages
sont écrits dans le journal en développement et jamais en production.
"""

import asyncio
import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Protocol

from app.config import Settings

logger = logging.getLogger("ludifun.email")


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    body: str


class EmailSender(Protocol):
    async def send(self, email: Email) -> None: ...


class LogEmailSender:
    """En attendant un fournisseur d'e-mails : journalise le message.

    Le contenu (lien de réinitialisation compris) n'est écrit qu'en développement ;
    en production, seul le fait qu'aucun e-mail n'a pu partir est journalisé.
    """

    def __init__(self, include_body: bool) -> None:
        self.include_body = include_body

    async def send(self, email: Email) -> None:
        if self.include_body:
            logger.info("E-mail pour %s : %s\n%s", email.to, email.subject, email.body)
        else:
            logger.warning("Aucun fournisseur d'e-mails configuré : « %s » non envoyé.", email.subject)


class EmailNotSent(Exception):
    """Le fournisseur a refusé le message ou n'a pas répondu."""


@dataclass(frozen=True)
class SmtpEmailSender:
    """Envoi par SMTP authentifié, chiffré (STARTTLS sur 587, TLS direct sur 465).

    La bibliothèque standard est synchrone : l'envoi part dans un fil à part pour ne pas
    bloquer l'API. Le journal ne cite jamais le destinataire ni le contenu.
    """

    host: str
    port: int
    username: str | None
    password: str | None
    sender: str
    timeout_s: float = 15.0

    def _message(self, email: Email) -> EmailMessage:
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = email.to
        message["Subject"] = email.subject
        message["Message-ID"] = make_msgid(domain=self.sender.rsplit("@", 1)[-1].strip(">"))
        message.set_content(email.body)
        return message

    def _send(self, email: Email) -> None:
        context = ssl.create_default_context()
        smtp: smtplib.SMTP
        if self.port == 465:
            smtp = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout_s, context=context)
        else:
            smtp = smtplib.SMTP(self.host, self.port, timeout=self.timeout_s)
        with smtp:
            if self.port != 465:
                smtp.starttls(context=context)
            if self.username:
                smtp.login(self.username, self.password or "")
            smtp.send_message(self._message(email))

    async def send(self, email: Email) -> None:
        try:
            await asyncio.to_thread(self._send, email)
        except (smtplib.SMTPException, OSError) as exc:
            logger.error("Envoi de « %s » impossible : %s", email.subject, type(exc).__name__)
            raise EmailNotSent from exc


@dataclass
class MemoryEmailSender:
    """Tests : garde les e-mails envoyés."""

    sent: list[Email] = field(default_factory=list)

    async def send(self, email: Email) -> None:
        self.sent.append(email)


def build_email_sender(settings: Settings) -> EmailSender:
    """SMTP si `LUDIFUN_SMTP_HOST` est défini ; sinon le journal (contenu en développement seulement)."""
    if settings.smtp_host:
        return SmtpEmailSender(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password.get_secret_value() if settings.smtp_password else None,
            sender=settings.email_from,
        )
    if settings.environment == "prod":
        logger.warning("LUDIFUN_SMTP_HOST absent : aucun e-mail ne partira.")
    return LogEmailSender(include_body=settings.environment != "prod")
