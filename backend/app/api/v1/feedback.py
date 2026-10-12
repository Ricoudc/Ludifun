"""Avis des familles (étape 18) : une note et/ou un message, du parent ou de l'enfant."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import select

from app import clock
from app.api.deps import (
    DbSession,
    DevicePrincipal,
    ParentPrincipal,
    Principal,
    current_principal,
    rate_limit,
)
from app.api.errors import ApiError
from app.db.models import Feedback, RevisionSession
from app.services import accounts

router = APIRouter(tags=["avis"])

Message = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
Screen = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[a-z_]{1,40}$")]
FEEDBACK_PER_DAY = 30


class FeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rating: int | None = Field(None, ge=1, le=5, description="1 à 5 (enfant : 1 😕, 3 🙂, 5 😍).")
    message: Message | None = None
    screen: Screen | None = Field(None, description="D'où vient l'avis : report, settings…")
    session_id: uuid.UUID | None = Field(None, description="Séance concernée (enfant).")
    child_id: uuid.UUID | None = Field(None, description="Enfant concerné (parent, facultatif).")

    @model_validator(mode="after")
    def _not_empty(self) -> "FeedbackIn":
        if self.rating is None and self.message is None:
            raise ValueError("une note ou un message")
        return self


class FeedbackAccepted(BaseModel):
    id: uuid.UUID


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
async def send_feedback(
    body: FeedbackIn,
    request: Request,
    db: DbSession,
    principal: Annotated[Principal, Depends(current_principal)],
) -> FeedbackAccepted:
    """L'avis n'est lu que par l'équipe Ludifun, pour améliorer l'application ; il est supprimé
    avec le compte ou le profil de son auteur."""
    parent_id = principal.parent_id if isinstance(principal, ParentPrincipal) else None
    child_id = principal.child_id if isinstance(principal, DevicePrincipal) else None
    rate_limit(request, f"feedback:{parent_id or child_id}", limit=FEEDBACK_PER_DAY, window_s=86400)
    if parent_id is not None:
        if body.session_id is not None:
            raise ApiError(422, "invalid_request", "session_id est réservé à l'enfant.")
        if body.child_id is not None and await accounts.child_of_parent(db, parent_id, body.child_id) is None:
            raise ApiError(404, "child_not_found", "Enfant introuvable.")
        child_id = body.child_id
    elif body.child_id not in (None, child_id):
        raise ApiError(404, "child_not_found", "Enfant introuvable.")
    if body.session_id is not None:
        owned = await db.scalar(
            select(RevisionSession.id).where(
                RevisionSession.id == body.session_id, RevisionSession.child_id == child_id
            )
        )
        if owned is None:
            raise ApiError(404, "session_not_found", "Séance introuvable.")
    feedback = Feedback(
        parent_id=parent_id,
        child_id=child_id,
        author="parent" if parent_id else "child",
        rating=body.rating,
        message=body.message,
        screen=body.screen,
        session_id=body.session_id,
        created_at=clock.now(),
    )
    db.add(feedback)
    await db.commit()
    return FeedbackAccepted(id=feedback.id)
