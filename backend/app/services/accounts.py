"""Comptes parent, familles, enfants et liaison des appareils (cahier des charges §11 et §16.1)."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import (
    Child,
    Device,
    EmailVerificationToken,
    Family,
    FamilyMember,
    LinkCode,
    Parent,
    PasswordResetToken,
    RefreshToken,
)
from app.security import tokens
from app.security.passwords import hash_password, needs_rehash, verify_password
from app.services.email import Email, EmailNotSent, EmailSender


class EmailTaken(Exception):
    pass


class InvalidCredentials(Exception):
    pass


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int  # secondes de validité du jeton d'accès


def normalize_email(email: str) -> str:
    return email.strip().lower()


# --------------------------------------------------------------------------- #
# Parent : inscription, connexion, jetons
# --------------------------------------------------------------------------- #


async def register_parent(db: AsyncSession, email: str, password: str, now: datetime) -> Parent:
    email = normalize_email(email)
    if await db.scalar(select(Parent.id).where(Parent.email == email)):
        raise EmailTaken
    parent = Parent(email=email, password_hash=hash_password(password), privacy_accepted_at=now)
    family = Family()
    db.add_all([parent, family])
    try:
        await db.flush()
    except IntegrityError as exc:  # inscription simultanée avec le même e-mail
        await db.rollback()
        raise EmailTaken from exc
    db.add(FamilyMember(family_id=family.id, parent_id=parent.id, role="owner"))
    await db.flush()
    return parent


async def authenticate(db: AsyncSession, email: str, password: str, now: datetime) -> Parent:
    parent = await db.scalar(select(Parent).where(Parent.email == normalize_email(email)))
    # Même vérification (et même durée) que l'e-mail existe ou non.
    if not verify_password(parent.password_hash if parent else None, password) or parent is None:
        raise InvalidCredentials
    if needs_rehash(parent.password_hash):
        parent.password_hash = hash_password(password)
    parent.last_login_at = now
    return parent


async def issue_tokens(
    db: AsyncSession, parent_id: uuid.UUID, settings: Settings, now: datetime
) -> TokenPair:
    refresh = tokens.opaque_token(tokens.REFRESH_PREFIX)
    db.add(
        RefreshToken(
            parent_id=parent_id,
            token_hash=refresh.hash,
            expires_at=now + timedelta(days=settings.refresh_token_days),
        )
    )
    await db.flush()
    lifetime = timedelta(minutes=settings.access_token_minutes)
    access = tokens.create_access_token(parent_id, settings.jwt_secret.get_secret_value(), now, lifetime)
    return TokenPair(access, refresh.value, int(lifetime.total_seconds()))


async def rotate_refresh_token(db: AsyncSession, token: str, settings: Settings, now: datetime) -> TokenPair:
    """Échange un jeton de renouvellement contre une nouvelle paire.

    Présenter un jeton déjà utilisé signale un vol probable : toute la chaîne de
    jetons du parent est révoquée et il doit se reconnecter.
    """
    stored = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == tokens.sha256(token)).with_for_update()
    )
    if stored is None or stored.expires_at <= now:
        raise InvalidCredentials
    if stored.revoked_at is not None:
        await revoke_all_refresh_tokens(db, stored.parent_id, now)
        raise InvalidCredentials
    pair = await issue_tokens(db, stored.parent_id, settings, now)
    new = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == tokens.sha256(pair.refresh_token))
    )
    assert new is not None
    stored.revoked_at, stored.replaced_by = now, new.id
    return pair


async def revoke_refresh_token(db: AsyncSession, token: str, now: datetime) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == tokens.sha256(token), RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


async def revoke_all_refresh_tokens(db: AsyncSession, parent_id: uuid.UUID, now: datetime) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.parent_id == parent_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


async def request_password_reset(
    db: AsyncSession, email: str, settings: Settings, sender: EmailSender, now: datetime
) -> None:
    """Envoie un lien si le compte existe ; ne révèle jamais si l'e-mail est connu."""
    parent = await db.scalar(select(Parent).where(Parent.email == normalize_email(email)))
    if parent is None:
        return
    reset = tokens.opaque_token(tokens.RESET_PREFIX)
    db.add(
        PasswordResetToken(
            parent_id=parent.id,
            token_hash=reset.hash,
            expires_at=now + timedelta(minutes=settings.password_reset_minutes),
        )
    )
    await db.flush()
    await sender.send(
        Email(
            to=parent.email,
            subject="Ludifun : réinitialisation du mot de passe",
            body=(
                "Pour choisir un nouveau mot de passe, ouvrez ce lien dans l'application "
                f"(valable {settings.password_reset_minutes} minutes) :\n"
                f"{settings.password_reset_url}{reset.value}\n\n"
                "Si vous n'avez rien demandé, ignorez ce message."
            ),
        )
    )


async def send_email_verification(
    db: AsyncSession, parent: Parent, settings: Settings, sender: EmailSender, now: datetime
) -> bool:
    """« Confirmez votre adresse » : un lien valable 7 jours ; les liens précédents restent
    valables jusqu'à leur expiration. Faux si l'e-mail n'a pas pu partir (on réessaiera)."""
    link = tokens.opaque_token(tokens.VERIFY_PREFIX)
    db.add(
        EmailVerificationToken(
            parent_id=parent.id,
            token_hash=link.hash,
            expires_at=now + timedelta(days=settings.email_verification_days),
        )
    )
    await db.flush()
    try:
        await sender.send(
            Email(
                to=parent.email,
                subject="Ludifun : confirmez votre adresse e-mail",
                body=(
                    "Bienvenue sur Ludifun !\n\n"
                    "Pour confirmer que cette adresse est bien la vôtre, ouvrez ce lien "
                    f"(valable {settings.email_verification_days} jours) :\n"
                    f"{settings.email_verification_url}{link.value}\n\n"
                    "Elle ne sert qu'à votre compte : mot de passe oublié et messages importants "
                    "sur les données de vos enfants. Jamais de publicité.\n\n"
                    "Si vous n'avez pas créé de compte, ignorez ce message : sans confirmation, "
                    "le compte ne recevra plus rien de notre part."
                ),
            )
        )
    except EmailNotSent:
        return False
    return True


async def verify_email(db: AsyncSession, token: str, now: datetime) -> Parent:
    link = await db.scalar(
        select(EmailVerificationToken)
        .where(EmailVerificationToken.token_hash == tokens.sha256(token))
        .with_for_update()
    )
    if link is None or link.expires_at <= now:
        raise InvalidCredentials
    parent = await db.get(Parent, link.parent_id)
    assert parent is not None
    if link.used_at is None:
        link.used_at = now
    if parent.email_verified_at is None:
        parent.email_verified_at = now
    return parent


async def reset_password(db: AsyncSession, token: str, new_password: str, now: datetime) -> None:
    reset = await db.scalar(
        select(PasswordResetToken)
        .where(PasswordResetToken.token_hash == tokens.sha256(token))
        .with_for_update()
    )
    if reset is None or reset.used_at is not None or reset.expires_at <= now:
        raise InvalidCredentials
    parent = await db.get(Parent, reset.parent_id)
    assert parent is not None
    parent.password_hash = hash_password(new_password)
    reset.used_at = now
    # Les autres liens de réinitialisation encore valables ne servent plus.
    await db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.parent_id == parent.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    await revoke_all_refresh_tokens(db, parent.id, now)  # déconnecte les autres téléphones


async def delete_parent(db: AsyncSession, parent_id: uuid.UUID) -> None:
    """Supprime le parent et les familles dont il est propriétaire, avec tous leurs enfants."""
    owned = select(FamilyMember.family_id).where(
        FamilyMember.parent_id == parent_id, FamilyMember.role == "owner"
    )
    await db.execute(delete(Family).where(Family.id.in_(owned)))
    await db.execute(delete(Parent).where(Parent.id == parent_id))


# --------------------------------------------------------------------------- #
# Enfants
# --------------------------------------------------------------------------- #


def _family_ids(parent_id: uuid.UUID) -> Select[tuple[uuid.UUID]]:
    return select(FamilyMember.family_id).where(FamilyMember.parent_id == parent_id)


async def list_children(db: AsyncSession, parent_id: uuid.UUID) -> list[Child]:
    result = await db.scalars(
        select(Child).where(Child.family_id.in_(_family_ids(parent_id))).order_by(Child.created_at)
    )
    return list(result)


async def child_of_parent(db: AsyncSession, parent_id: uuid.UUID, child_id: uuid.UUID) -> Child | None:
    """L'enfant, seulement s'il appartient à une famille du parent."""
    child: Child | None = await db.scalar(
        select(Child).where(Child.id == child_id, Child.family_id.in_(_family_ids(parent_id)))
    )
    return child


async def create_child(
    db: AsyncSession, parent_id: uuid.UUID, display_name: str, grade: str, avatar: str | None, now: datetime
) -> Child:
    family_id = await db.scalar(
        select(FamilyMember.family_id).where(
            FamilyMember.parent_id == parent_id, FamilyMember.role == "owner"
        )
    )
    assert family_id is not None
    child = Child(
        family_id=family_id, display_name=display_name, grade=grade, avatar=avatar, parental_consent_at=now
    )
    db.add(child)
    await db.flush()
    return child


async def active_devices_count(db: AsyncSession, child_id: uuid.UUID) -> int:
    count = await db.scalar(
        select(func.count())
        .select_from(Device)
        .where(Device.child_id == child_id, Device.revoked_at.is_(None))
    )
    return count or 0


# --------------------------------------------------------------------------- #
# Liaison des appareils
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class IssuedLinkCode:
    code: str
    qr_token: str
    expires_at: datetime


async def create_link_code(
    db: AsyncSession, child: Child, settings: Settings, now: datetime
) -> IssuedLinkCode:
    """Nouveau code (6 chiffres) et jeton de QR code ; les codes précédents de l'enfant sont annulés."""
    await db.execute(
        update(LinkCode)
        .where(LinkCode.child_id == child.id, LinkCode.used_at.is_(None))
        .values(expires_at=now)
    )
    # Deux codes actifs identiques rendraient la liaison ambiguë : on en tire un autre.
    while True:
        code = tokens.link_code()
        clash = await db.scalar(
            select(LinkCode.id).where(
                LinkCode.code_hash == tokens.sha256(code),
                LinkCode.used_at.is_(None),
                LinkCode.expires_at > now,
            )
        )
        if clash is None:
            break
    qr = tokens.opaque_token("", nbytes=16)
    expires_at = now + timedelta(minutes=settings.link_code_minutes)
    db.add(
        LinkCode(
            child_id=child.id, code_hash=tokens.sha256(code), qr_token_hash=qr.hash, expires_at=expires_at
        )
    )
    await db.flush()
    return IssuedLinkCode(code, qr.value, expires_at)


@dataclass(frozen=True)
class LinkedDevice:
    child: Child
    device: Device
    token: str


async def redeem_link_code(
    db: AsyncSession, code: str | None, qr_token: str | None, device_name: str | None, now: datetime
) -> LinkedDevice | None:
    """Échange un code (ou le jeton du QR code) contre un jeton d'appareil, une seule fois."""
    condition = (
        LinkCode.code_hash == tokens.sha256(code)
        if code is not None
        else LinkCode.qr_token_hash == tokens.sha256(qr_token or "")
    )
    link = await db.scalar(
        select(LinkCode)
        .where(condition, LinkCode.used_at.is_(None), LinkCode.expires_at > now)
        .with_for_update()
    )
    if link is None:
        return None
    link.used_at = now
    child = await db.get(Child, link.child_id)
    assert child is not None
    token = tokens.opaque_token(tokens.DEVICE_PREFIX)
    device = Device(child_id=child.id, token_hash=token.hash, name=device_name, last_seen_at=now)
    db.add(device)
    await db.flush()
    return LinkedDevice(child, device, token.value)


async def authenticate_device(db: AsyncSession, token: str, now: datetime) -> Device | None:
    device = await db.scalar(
        select(Device).where(Device.token_hash == tokens.sha256(token), Device.revoked_at.is_(None))
    )
    if device is not None and (
        device.last_seen_at is None or now - device.last_seen_at > timedelta(minutes=5)
    ):
        device.last_seen_at = now
    return device


async def list_devices(db: AsyncSession, child_id: uuid.UUID) -> list[Device]:
    result = await db.scalars(
        select(Device)
        .where(Device.child_id == child_id, Device.revoked_at.is_(None))
        .order_by(Device.created_at)
    )
    return list(result)


async def revoke_device(db: AsyncSession, child_id: uuid.UUID, device_id: uuid.UUID, now: datetime) -> bool:
    result = await db.execute(
        update(Device)
        .where(Device.id == device_id, Device.child_id == child_id, Device.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    return bool(result.rowcount)  # type: ignore[attr-defined]
