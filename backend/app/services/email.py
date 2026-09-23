"""Envoi d'e-mails aux parents (réinitialisation du mot de passe…).

V1 : les messages sont écrits dans le journal. Un fournisseur d'e-mails réel sera
branché avant la bêta publique, derrière la même interface.
"""

import logging
from dataclasses import dataclass, field
from typing import Protocol

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


@dataclass
class MemoryEmailSender:
    """Tests : garde les e-mails envoyés."""

    sent: list[Email] = field(default_factory=list)

    async def send(self, email: Email) -> None:
        self.sent.append(email)
