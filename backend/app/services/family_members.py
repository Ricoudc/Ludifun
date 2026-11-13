"""Second parent (§5.92) : inviter un autre parent dans sa famille, le rejoindre, le retirer.

Le parent qui invite est propriétaire (`owner`) de la famille ; celui qui rejoint en devient
membre (`member`) et voit les mêmes enfants, leçons et réglages. Pour qu'il n'y ait jamais deux
familles qui se contredisent, on ne rejoint une famille que si la sienne est vide (aucun enfant) :
elle est alors supprimée. Supprimer son compte, pour un membre, ne touche pas la famille.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Child, Family, FamilyInvite, FamilyMember, Parent
from app.security import tokens

INVITE_DAYS = 7
MAX_MEMBERS = 2  # le propriétaire et un second parent


class FamilyError(Exception):
    def __init__(self, code: str, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


@dataclass(frozen=True)
class Member:
    parent_id: uuid.UUID
    email: str
    first_name: str | None
    role: Literal["owner", "member"]


async def owned_family(db: AsyncSession, parent_id: uuid.UUID) -> uuid.UUID | None:
    family: uuid.UUID | None = await db.scalar(
        select(FamilyMember.family_id).where(
            FamilyMember.parent_id == parent_id, FamilyMember.role == "owner"
        )
    )
    return family


async def members(db: AsyncSession, family_id: uuid.UUID) -> list[Member]:
    rows = await db.execute(
        select(Parent.id, Parent.email, Parent.first_name, FamilyMember.role)
        .join(FamilyMember, FamilyMember.parent_id == Parent.id)
        .where(FamilyMember.family_id == family_id)
        .order_by(FamilyMember.role.desc(), Parent.created_at)  # « owner » avant « member »
    )
    return [Member(r.id, r.email, r.first_name, r.role) for r in rows]


async def create_invite(db: AsyncSession, parent_id: uuid.UUID, now: datetime) -> tuple[str, datetime]:
    family_id = await owned_family(db, parent_id)
    if family_id is None:
        raise FamilyError("owner_only", "Seul le parent qui a créé la famille peut inviter.", 403)
    if len(await members(db, family_id)) >= MAX_MEMBERS:
        raise FamilyError("family_full", "Un second parent a déjà rejoint la famille.")
    # Une seule invitation active : la précédente ne sert plus.
    await db.execute(
        update(FamilyInvite)
        .where(FamilyInvite.family_id == family_id, FamilyInvite.used_at.is_(None))
        .values(expires_at=now)
    )
    code = tokens.invite_code()
    expires_at = now + timedelta(days=INVITE_DAYS)
    db.add(FamilyInvite(family_id=family_id, code_hash=tokens.sha256(code), expires_at=expires_at))
    await db.flush()
    return code, expires_at


async def join(db: AsyncSession, parent_id: uuid.UUID, code: str, now: datetime) -> uuid.UUID:
    invite = await db.scalar(
        select(FamilyInvite)
        .where(
            FamilyInvite.code_hash == tokens.sha256(tokens.normalize_invite_code(code)),
            FamilyInvite.used_at.is_(None),
            FamilyInvite.expires_at > now,
        )
        .with_for_update()
    )
    if invite is None:
        raise FamilyError("invite_invalid", "Code d'invitation inconnu ou expiré.", 404)
    if await db.scalar(
        select(FamilyMember.parent_id).where(
            FamilyMember.family_id == invite.family_id, FamilyMember.parent_id == parent_id
        )
    ):
        raise FamilyError("already_member", "Vous faites déjà partie de cette famille.")
    if len(await members(db, invite.family_id)) >= MAX_MEMBERS:
        raise FamilyError("family_full", "Un second parent a déjà rejoint la famille.")
    own = await owned_family(db, parent_id)
    if own is not None:
        children = await db.scalar(select(func.count()).select_from(Child).where(Child.family_id == own))
        if children:
            raise FamilyError(
                "own_family_not_empty",
                "Votre compte a déjà des enfants : pour rejoindre une autre famille, utilisez un "
                "compte sans enfant.",
            )
        await db.execute(delete(Family).where(Family.id == own))
    db.add(FamilyMember(family_id=invite.family_id, parent_id=parent_id, role="member"))
    invite.used_at = now
    await db.flush()
    return invite.family_id


async def remove_member(db: AsyncSession, parent_id: uuid.UUID, member_id: uuid.UUID) -> None:
    """Le propriétaire retire le second parent, ou le second parent quitte la famille. Celui qui
    part retrouve une famille à lui, vide."""
    family_id = await owned_family(db, parent_id) if parent_id != member_id else None
    if family_id is None:
        family_id = await db.scalar(
            select(FamilyMember.family_id).where(
                FamilyMember.parent_id == member_id, FamilyMember.role == "member"
            )
        )
    gone = await db.scalar(
        select(FamilyMember).where(
            FamilyMember.family_id == family_id,
            FamilyMember.parent_id == member_id,
            FamilyMember.role == "member",
        )
    )
    if family_id is None or gone is None:
        raise FamilyError("member_not_found", "Parent introuvable dans la famille.", 404)
    await db.delete(gone)
    if await owned_family(db, member_id) is None:
        family = Family()
        db.add(family)
        await db.flush()
        db.add(FamilyMember(family_id=family.id, parent_id=member_id, role="owner"))
    await db.flush()
