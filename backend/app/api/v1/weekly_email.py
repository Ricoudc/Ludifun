"""Espace parent : le bilan de la semaine par e-mail (§5.93), au choix du parent."""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import CurrentParent, DbSession
from app.db.models import Parent

router = APIRouter(tags=["espace parent"])


class WeeklyEmailIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class WeeklyEmailOut(BaseModel):
    enabled: bool = Field(description="Le bilan de la semaine part chaque dimanche par e-mail.")
    email_verified: bool = Field(description="Sans adresse vérifiée, rien ne part.")


async def _out(db: DbSession, parent: CurrentParent) -> WeeklyEmailOut:
    row = (
        await db.execute(
            select(Parent.weekly_email, Parent.email_verified_at).where(Parent.id == parent.parent_id)
        )
    ).one()
    return WeeklyEmailOut(enabled=row.weekly_email, email_verified=row.email_verified_at is not None)


@router.get("/parent/weekly-email")
async def get_weekly_email(parent: CurrentParent, db: DbSession) -> WeeklyEmailOut:
    return await _out(db, parent)


@router.put("/parent/weekly-email")
async def set_weekly_email(body: WeeklyEmailIn, parent: CurrentParent, db: DbSession) -> WeeklyEmailOut:
    row = await db.get(Parent, parent.parent_id)
    assert row is not None
    row.weekly_email = body.enabled
    await db.commit()
    return await _out(db, parent)
