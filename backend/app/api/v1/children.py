"""Profils enfants (espace parent), liaison des appareils et profil vu par l'enfant."""

import uuid

from fastapi import APIRouter, Request, Response, status

from app import clock
from app.api.deps import (
    AppSettings,
    ChildInScope,
    CurrentDevice,
    CurrentParent,
    DbSession,
    client_ip,
    rate_limit,
)
from app.api.errors import ApiError
from app.api.v1.schemas import (
    ChildIn,
    ChildOut,
    ChildPatch,
    ChildPublic,
    DeviceOut,
    LinkCodeOut,
    LinkIn,
    LinkOut,
)
from app.db.models import Child
from app.services import accounts

router = APIRouter()

CHILD_NOT_FOUND = ApiError(404, "child_not_found", "Enfant introuvable.")
QR_PREFIX = "ludifun://lier/"
# Plafond global d'échecs de liaison : protège les codes à 6 chiffres contre une attaque
# répartie sur de nombreuses adresses IP. Le QR code (jeton de 128 bits) reste la voie forte.
GLOBAL_LINK_FAILURES = ("link-failures", 300, 60.0)


async def child_out(db: DbSession, child: Child) -> ChildOut:
    return ChildOut(
        id=child.id,
        display_name=child.display_name,
        grade=child.grade,
        avatar=child.avatar,
        created_at=child.created_at,
        devices=await accounts.active_devices_count(db, child.id),
    )


async def own_child(db: DbSession, parent: CurrentParent, child_id: uuid.UUID) -> Child:
    child = await accounts.child_of_parent(db, parent.parent_id, child_id)
    if child is None:
        raise CHILD_NOT_FOUND
    return child


# --------------------------------------------------------------------------- #
# Espace parent
# --------------------------------------------------------------------------- #


@router.get("/children", tags=["enfants"])
async def list_children(parent: CurrentParent, db: DbSession) -> list[ChildOut]:
    return [await child_out(db, c) for c in await accounts.list_children(db, parent.parent_id)]


@router.post("/children", status_code=status.HTTP_201_CREATED, tags=["enfants"])
async def create_child(body: ChildIn, parent: CurrentParent, db: DbSession) -> ChildOut:
    child = await accounts.create_child(
        db, parent.parent_id, body.display_name, body.grade, body.avatar, clock.now()
    )
    await db.commit()
    await db.refresh(child)
    return await child_out(db, child)


@router.patch("/children/{child_id}", tags=["enfants"])
async def update_child(
    child_id: uuid.UUID, body: ChildPatch, parent: CurrentParent, db: DbSession
) -> ChildOut:
    child = await own_child(db, parent, child_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is None and field != "avatar":
            raise ApiError(422, "invalid_request", f"{field} ne peut pas être vide.")
        setattr(child, field, value)
    await db.commit()
    return await child_out(db, child)


@router.delete("/children/{child_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["enfants"])
async def delete_child(child_id: uuid.UUID, parent: CurrentParent, db: DbSession) -> Response:
    """Supprime l'enfant et toutes ses données : leçons, séances, maîtrise, appareils liés."""
    await db.delete(await own_child(db, parent, child_id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/children/{child_id}/link-codes", status_code=status.HTTP_201_CREATED, tags=["liaison"])
async def create_link_code(
    child_id: uuid.UUID, parent: CurrentParent, db: DbSession, settings: AppSettings
) -> LinkCodeOut:
    issued = await accounts.create_link_code(db, await own_child(db, parent, child_id), settings, clock.now())
    await db.commit()
    return LinkCodeOut(code=issued.code, qr=QR_PREFIX + issued.qr_token, expires_at=issued.expires_at)


@router.get("/children/{child_id}/devices", tags=["liaison"])
async def list_devices(child_id: uuid.UUID, parent: CurrentParent, db: DbSession) -> list[DeviceOut]:
    child = await own_child(db, parent, child_id)
    return [DeviceOut.model_validate(d) for d in await accounts.list_devices(db, child.id)]


@router.delete(
    "/children/{child_id}/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["liaison"]
)
async def revoke_device(
    child_id: uuid.UUID, device_id: uuid.UUID, parent: CurrentParent, db: DbSession
) -> Response:
    child = await own_child(db, parent, child_id)
    if not await accounts.revoke_device(db, child.id, device_id, clock.now()):
        raise ApiError(404, "device_not_found", "Appareil introuvable.")
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- #
# Espace enfant
# --------------------------------------------------------------------------- #


@router.post("/link", status_code=status.HTTP_201_CREATED, tags=["liaison"])
async def link_device(body: LinkIn, request: Request, db: DbSession) -> LinkOut:
    """Écran 0 : l'appareil de l'enfant échange le code (ou le QR code) contre son jeton."""
    rate_limit(request, f"link:{client_ip(request)}", limit=10, window_s=600)
    key, limit, window = GLOBAL_LINK_FAILURES
    rate_limit(request, key, limit, window, record=False)
    qr_token = body.qr_token.removeprefix(QR_PREFIX) if body.qr_token else None
    linked = await accounts.redeem_link_code(db, body.code, qr_token, body.device_name, clock.now())
    if linked is None:
        request.app.state.rate_limiter.hit(key, limit, window)
        raise ApiError(
            400, "invalid_link_code", "Ce code ne marche pas. Demande un nouveau code à ton parent."
        )
    await db.commit()
    return LinkOut(
        token=linked.token, device_id=linked.device.id, child=ChildPublic.model_validate(linked.child)
    )


@router.get("/me", tags=["enfant"])
async def me(child: ChildInScope) -> ChildPublic:
    return ChildPublic.model_validate(child)


@router.delete("/me/device", status_code=status.HTTP_204_NO_CONTENT, tags=["enfant"])
async def unlink_this_device(device: CurrentDevice, db: DbSession) -> Response:
    """« Ce n'est pas moi » après la liaison : l'appareil rend son jeton."""
    await accounts.revoke_device(db, device.child_id, device.device_id, clock.now())
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
