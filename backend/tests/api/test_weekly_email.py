"""Bilan de la semaine par e-mail (§5.93) : au choix du parent, le dimanche, une fois par semaine,
aux adresses vérifiées seulement ; le texte reprend « En bref » et « Cette semaine »."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Parent
from app.domain.weekly_email import ChildWeek, body, subject
from app.services.email import MemoryEmailSender
from app.services.weekly_email import send_weekly_emails
from tests.api.helpers import auth, family_with_device, upload_lesson

SUNDAY = datetime(2026, 11, 15, 17, 0, tzinfo=UTC)  # 18 h à Paris


def test_the_text_names_each_child_and_what_to_do() -> None:
    weeks = [
        ChildWeek("Emma", ["3 séances, 45 minutes."], [("Revoir les fractions", "deux séances courtes")]),
        ChildWeek("Léo"),
    ]
    text = body("Claire", weeks, "Le détail est dans l'application.")
    assert subject(weeks) == "Ludifun : la semaine de Emma, Léo"
    assert text.startswith("Bonjour Claire,")
    assert "— Emma —\n• 3 séances, 45 minutes." in text
    assert "  – Revoir les fractions : deux séances courtes" in text
    assert "— Léo —\n• Pas de révision cette semaine." in text
    assert "Vous pouvez l'arrêter" in text


async def test_the_weekly_email_is_chosen_sent_on_sunday_and_once(
    client: AsyncClient, db: AsyncSession
) -> None:
    family = await family_with_device(client)
    parent = auth(family["parent"])
    await upload_lesson(client, family["device"])
    assert (await client.get("/v1/parent/weekly-email", headers=parent)).json() == {
        "enabled": False,
        "email_verified": False,
    }
    sender, settings = MemoryEmailSender(), Settings()
    # Désactivé par défaut : rien ne part.
    assert (await send_weekly_emails(db, settings, sender, SUNDAY)).sent == 0

    r = await client.put("/v1/parent/weekly-email", json={"enabled": True}, headers=parent)
    assert r.status_code == 200 and r.json()["enabled"] is True
    # Adresse non vérifiée : rien ne part non plus.
    assert (await send_weekly_emails(db, settings, sender, SUNDAY)).sent == 0
    await db.execute(update(Parent).values(email_verified_at=SUNDAY - timedelta(days=30)))
    await db.commit()

    # Un samedi : rien. Le dimanche : un e-mail, avec l'enfant.
    saturday = await send_weekly_emails(db, settings, sender, SUNDAY - timedelta(days=1))
    assert saturday.skipped_not_today and sender.sent == []
    sent = await send_weekly_emails(db, settings, sender, SUNDAY)
    assert sent.sent == 1 and len(sender.sent) == 1
    email = sender.sent[0]
    assert email.to == "parent@example.fr" and "Emma" in email.subject and "— Emma —" in email.body
    # Relancé le même dimanche : pas de second envoi ; le dimanche suivant : un nouveau.
    assert (await send_weekly_emails(db, settings, sender, SUNDAY + timedelta(hours=2))).sent == 0
    assert (await send_weekly_emails(db, settings, sender, SUNDAY + timedelta(days=7))).sent == 1

    # Le parent arrête : plus rien.
    await client.put("/v1/parent/weekly-email", json={"enabled": False}, headers=parent)
    assert (await send_weekly_emails(db, settings, sender, SUNDAY + timedelta(days=14))).sent == 0
