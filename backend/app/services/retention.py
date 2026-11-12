"""Conservation des données (cahier des charges V1 §16.2) : un compte inactif depuis 12 mois est
supprimé, après un e-mail de prévenance envoyé au moins 30 jours avant.

« Actif » : le parent s'est connecté ou a utilisé l'application (jeton renouvelé), ou l'un de
ses enfants a révisé sur un appareil lié. Revenir, même une fois, annule la prévenance.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Child, Device, FamilyMember, Parent, RefreshToken
from app.services import accounts
from app.services.email import Email, EmailNotSent, EmailSender

logger = logging.getLogger("ludifun.retention")


async def last_activity(db: AsyncSession, parent: Parent) -> datetime:
    refreshed = await db.scalar(
        select(func.max(RefreshToken.created_at)).where(RefreshToken.parent_id == parent.id)
    )
    families = select(FamilyMember.family_id).where(FamilyMember.parent_id == parent.id)
    seen = await db.scalar(
        select(func.max(Device.last_seen_at))
        .join(Child, Child.id == Device.child_id)
        .where(Child.family_id.in_(families))
    )
    return max(at for at in (parent.created_at, parent.last_login_at, refreshed, seen) if at is not None)


@dataclass
class RetentionRun:
    warned: list[uuid.UUID] = field(default_factory=list)
    deleted: list[uuid.UUID] = field(default_factory=list)
    failed: list[uuid.UUID] = field(default_factory=list)  # prévenance non partie : on réessaiera


def _warning(parent: Parent, deletion: datetime) -> Email:
    return Email(
        to=parent.email,
        subject="Ludifun : votre compte sera supprimé faute d'utilisation",
        body=(
            f"{accounts.greeting(parent)}\n\n"
            "Votre compte Ludifun n'a pas été utilisé depuis près d'un an. Pour ne pas garder les "
            "données de vos enfants inutilement, il sera supprimé avec toutes ses données (profils, "
            f"leçons, résultats) à partir du {deletion:%d/%m/%Y}.\n\n"
            "Pour le garder, il suffit d'ouvrir l'application et de vous connecter, ou que votre "
            "enfant fasse une révision. Pour récupérer les données avant, utilisez « Exporter les "
            "données » dans les réglages de chaque enfant.\n\n"
            "À bientôt peut-être !"
        ),
    )


async def apply_retention(
    db: AsyncSession, settings: Settings, sender: EmailSender, now: datetime, dry_run: bool = False
) -> RetentionRun:
    """Prévient puis supprime. Chaque compte est validé à part : une erreur n'arrête pas les autres."""
    run = RetentionRun()
    warn_before = now - timedelta(days=settings.inactive_warning_days)
    parents = list(await db.scalars(select(Parent).where(Parent.created_at <= warn_before)))
    for parent in parents:
        active = await last_activity(db, parent)
        if active > warn_before:
            continue
        warned = parent.inactivity_warned_at
        if warned is not None and warned > active:
            notice_over = warned + timedelta(days=settings.inactive_notice_days) <= now
            if notice_over and active <= now - timedelta(days=settings.inactive_delete_days):
                run.deleted.append(parent.id)
                if not dry_run:
                    await accounts.delete_parent(db, parent.id)
                    await db.commit()
            continue
        deletion = max(
            active + timedelta(days=settings.inactive_delete_days),
            now + timedelta(days=settings.inactive_notice_days),
        )
        if dry_run:
            run.warned.append(parent.id)
            continue
        try:
            await sender.send(_warning(parent, deletion))
        except EmailNotSent:
            run.failed.append(parent.id)
            continue
        parent.inactivity_warned_at = now
        await db.commit()
        run.warned.append(parent.id)
    logger.info(
        "Conservation : %d prévenu(s), %d supprimé(s), %d échec(s)%s",
        len(run.warned),
        len(run.deleted),
        len(run.failed),
        " (simulation)" if dry_run else "",
    )
    return run
