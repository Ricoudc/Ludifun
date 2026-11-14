"""Espace parent : un second parent dans la famille (§5.92)."""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app import clock
from app.api.deps import CurrentParent, DbSession, rate_limit
from app.api.errors import ApiError
from app.services import ai_settings, family_members
from app.services.family_members import FamilyError

router = APIRouter(tags=["espace parent"])


class MemberOut(BaseModel):
    parent_id: uuid.UUID
    email: str
    first_name: str | None = None
    role: Literal["owner", "member"]
    me: bool = Field(description="C'est le parent connecté.")


class MembersOut(BaseModel):
    members: list[MemberOut]
    can_invite: bool = Field(description="Le parent connecté peut inviter un second parent.")


class InviteOut(BaseModel):
    code: str = Field(description="À donner à l'autre parent : « ABCD-EFGH ».")
    expires_at: datetime


class JoinIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=8, max_length=20)


def _error(exc: FamilyError) -> ApiError:
    return ApiError(exc.status, exc.code, exc.message)


async def members_out(db: DbSession, parent: CurrentParent) -> MembersOut:
    family_id = await ai_settings.family_of_parent(db, parent.parent_id)
    if family_id is None:
        raise ApiError(404, "family_not_found", "Famille introuvable.")
    found = await family_members.members(db, family_id)
    me = next(m for m in found if m.parent_id == parent.parent_id)
    return MembersOut(
        members=[
            MemberOut(
                parent_id=m.parent_id,
                email=m.email,
                first_name=m.first_name,
                role=m.role,
                me=m.parent_id == parent.parent_id,
            )
            for m in found
        ],
        can_invite=me.role == "owner" and len(found) < family_members.MAX_MEMBERS,
    )


@router.get("/parent/members")
async def get_members(parent: CurrentParent, db: DbSession) -> MembersOut:
    """Les parents de la famille."""
    return await members_out(db, parent)


@router.post("/parent/invites", status_code=status.HTTP_201_CREATED)
async def create_invite(request: Request, parent: CurrentParent, db: DbSession) -> InviteOut:
    """Inviter un second parent : un code à lui donner, valable 7 jours, une seule fois."""
    rate_limit(request, f"invite:{parent.parent_id}", limit=10, window_s=3600)
    try:
        code, expires_at = await family_members.create_invite(db, parent.parent_id, clock.now())
    except FamilyError as exc:
        raise _error(exc) from exc
    await db.commit()
    return InviteOut(code=code, expires_at=expires_at)


@router.post("/parent/join")
async def join_family(body: JoinIn, request: Request, parent: CurrentParent, db: DbSession) -> MembersOut:
    """Rejoindre la famille d'un autre parent avec son code. Le compte ne doit pas avoir d'enfant."""
    rate_limit(request, f"join:{parent.parent_id}", limit=10, window_s=3600)
    try:
        await family_members.join(db, parent.parent_id, body.code, clock.now())
    except FamilyError as exc:
        await db.rollback()
        raise _error(exc) from exc
    await db.commit()
    return await members_out(db, parent)


@router.delete("/parent/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(member_id: uuid.UUID, parent: CurrentParent, db: DbSession) -> Response:
    """Le propriétaire retire le second parent, ou le second parent quitte la famille."""
    try:
        await family_members.remove_member(db, parent.parent_id, member_id)
    except FamilyError as exc:
        raise _error(exc) from exc
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
