"""Formats d'entrée et de sortie de l'API v1 (comptes et liaison)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

from app.domain.knowledge import Grade, Subject
from app.security.passwords import MAX_LENGTH, MIN_LENGTH

Password = Annotated[str, Field(min_length=MIN_LENGTH, max_length=MAX_LENGTH)]
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Avatar = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- #
# Parent
# --------------------------------------------------------------------------- #


class RegisterIn(_In):
    email: EmailStr
    password: Password
    accepted_privacy_policy: Literal[True] = Field(description="Doit valoir true.")


class LoginIn(_In):
    email: EmailStr
    password: Annotated[str, Field(max_length=MAX_LENGTH)]


class RefreshIn(_In):
    refresh_token: Annotated[str, Field(max_length=200)]


class PasswordResetIn(_In):
    email: EmailStr


class PasswordResetConfirmIn(_In):
    token: Annotated[str, Field(max_length=200)]
    new_password: Password


class ParentOut(BaseModel):
    id: uuid.UUID
    email: str


class TokensOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    parent: ParentOut


# --------------------------------------------------------------------------- #
# Enfants et appareils
# --------------------------------------------------------------------------- #


class ChildIn(_In):
    display_name: DisplayName = Field(description="Prénom ou pseudo.")
    grade: Grade
    avatar: Avatar | None = None
    parental_consent: Literal[True] = Field(description="Consentement parental (§16.2), doit valoir true.")


DailyMinutes = Literal[5, 10, 15, 20, 30]


class ChildPatch(_In):
    display_name: DisplayName | None = None
    grade: Grade | None = None
    avatar: Avatar | None = None
    daily_minutes: DailyMinutes | None = Field(None, description="Temps de révision par jour ; null : libre.")
    priority_subject: Subject | None = Field(None, description="Matière à privilégier ; null : aucune.")


class ChildPublic(BaseModel):
    """Ce que voit l'enfant sur son appareil."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str
    grade: Grade
    avatar: str | None


class ChildOut(ChildPublic):
    created_at: datetime
    devices: int = Field(description="Appareils liés actifs.")
    daily_minutes: int | None = None
    priority_subject: str | None = None


class LinkCodeOut(BaseModel):
    code: str = Field(description="Code à 6 chiffres à saisir sur l'appareil de l'enfant.")
    qr: str = Field(description="Contenu du QR code.")
    expires_at: datetime


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str | None
    created_at: datetime
    last_seen_at: datetime | None


class LinkIn(_In):
    code: Annotated[str, StringConstraints(pattern=r"^\d{6}$")] | None = None
    qr_token: Annotated[str, Field(min_length=10, max_length=100)] | None = None
    device_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None = None

    @model_validator(mode="after")
    def _one_of(self) -> Self:
        if (self.code is None) == (self.qr_token is None):
            raise ValueError("donner soit le code, soit le jeton du QR code")
        return self


class LinkOut(BaseModel):
    token: str = Field(description="Jeton de l'appareil, à conserver dans le stockage sécurisé.")
    device_id: uuid.UUID
    child: ChildPublic
