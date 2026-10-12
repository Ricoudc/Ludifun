"""Conservation (§16.2) : prévenance à 11 mois d'inactivité, suppression à 12 mois et au moins
30 jours après la prévenance ; toute activité (parent ou enfant) remet le compteur à zéro."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Child, Device, Parent
from app.services.email import Email, EmailNotSent, MemoryEmailSender
from app.services.retention import apply_retention
from tests.api.helpers import family_with_device, register

SETTINGS = Settings(environment="test")
DAY = timedelta(days=1)


async def parent_by_email(db: AsyncSession, email: str) -> Parent:
    db.expire_all()
    parent = await db.scalar(select(Parent).where(Parent.email == email))
    assert parent is not None
    return parent


async def remaining(db: AsyncSession) -> set[str]:
    return set(await db.scalars(select(Parent.email)))


async def test_inactive_account_is_warned_then_deleted(client: AsyncClient, db: AsyncSession) -> None:
    await register(client, "dormant@example.fr")
    await family_with_device(client, "actif@example.fr")
    start = datetime.now(UTC)
    mailer = MemoryEmailSender()

    # Quelqu'un révise sur la tablette d'Emma : sa famille reste active.
    device = await db.scalar(select(Device))
    assert device is not None
    device.last_seen_at = start + 300 * DAY
    await db.commit()

    run = await apply_retention(db, SETTINGS, mailer, start + 330 * DAY)
    assert run.warned == [] and mailer.sent == []

    day_336 = start + 336 * DAY
    run = await apply_retention(db, SETTINGS, mailer, day_336)
    assert [m.to for m in mailer.sent] == ["dormant@example.fr"]
    assert "sera supprimé" in mailer.sent[0].subject
    deletion = day_336 + 30 * DAY  # 12 mois, et au moins 30 jours après la prévenance
    assert f"à partir du {deletion:%d/%m/%Y}" in mailer.sent[0].body
    assert (await parent_by_email(db, "dormant@example.fr")).inactivity_warned_at == day_336

    # Pas de deuxième prévenance, pas de suppression avant 12 mois ni avant 30 jours de délai.
    for day in (340, 365):
        run = await apply_retention(db, SETTINGS, mailer, start + day * DAY)
        assert run.warned == run.deleted == [] and len(mailer.sent) == 1

    run = await apply_retention(db, SETTINGS, mailer, start + 366 * DAY)
    assert len(run.deleted) == 1
    assert await remaining(db) == {"actif@example.fr"}
    assert await db.scalar(select(func.count()).select_from(Child)) == 1  # seul Emma reste


async def test_coming_back_cancels_the_warning(client: AsyncClient, db: AsyncSession) -> None:
    await register(client, "revenu@example.fr")
    start = datetime.now(UTC)
    mailer = MemoryEmailSender()
    await apply_retention(db, SETTINGS, mailer, start + 340 * DAY)
    assert len(mailer.sent) == 1

    parent = await parent_by_email(db, "revenu@example.fr")
    parent.last_login_at = start + 350 * DAY
    await db.commit()
    run = await apply_retention(db, SETTINGS, mailer, start + 400 * DAY)
    assert run.deleted == [] and await remaining(db) == {"revenu@example.fr"}

    # Onze mois après ce retour : nouvelle prévenance.
    run = await apply_retention(db, SETTINGS, mailer, start + (350 + 336) * DAY)
    assert len(run.warned) == 1 and len(mailer.sent) == 2


async def test_dry_run_and_email_failure(client: AsyncClient, db: AsyncSession) -> None:
    await register(client, "dormant@example.fr")
    start = datetime.now(UTC)

    run = await apply_retention(db, SETTINGS, MemoryEmailSender(), start + 400 * DAY, dry_run=True)
    assert len(run.warned) == 1
    assert (await parent_by_email(db, "dormant@example.fr")).inactivity_warned_at is None

    class Broken:
        async def send(self, email: Email) -> None:
            raise EmailNotSent

    run = await apply_retention(db, SETTINGS, Broken(), start + 400 * DAY)
    assert len(run.failed) == 1 and run.warned == []
    # Sans prévenance partie, jamais de suppression.
    run = await apply_retention(db, SETTINGS, Broken(), start + 800 * DAY)
    assert run.deleted == [] and await remaining(db) == {"dormant@example.fr"}
