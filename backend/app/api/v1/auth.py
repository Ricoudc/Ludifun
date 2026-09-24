"""Compte parent : inscription, connexion, jetons, mot de passe, suppression."""

from fastapi import APIRouter, Request, Response, status

from app import clock
from app.api.deps import AppSettings, CurrentParent, DbSession, Mailer, client_ip, rate_limit
from app.api.errors import ApiError
from app.api.v1.schemas import (
    EmailVerificationIn,
    LoginIn,
    ParentOut,
    ParentPatch,
    PasswordResetConfirmIn,
    PasswordResetIn,
    RefreshIn,
    RegisterIn,
    TokensOut,
)
from app.db.models import Parent
from app.security.tokens import decode_access_token
from app.services import accounts
from app.services.email import EmailNotSent

router = APIRouter(tags=["compte parent"])

BAD_CREDENTIALS = ApiError(401, "invalid_credentials", "E-mail ou mot de passe incorrect.")


def tokens_out(pair: accounts.TokenPair, parent: Parent) -> TokensOut:
    return TokensOut(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.expires_in,
        parent=parent_out(parent),
    )


def parent_out(parent: Parent) -> ParentOut:
    return ParentOut(
        id=parent.id,
        email=parent.email,
        first_name=parent.first_name,
        email_verified=parent.email_verified_at is not None,
    )


INVALID_VERIFICATION = ApiError(
    400,
    "invalid_verification_token",
    "Ce lien n'est plus valable. Demandez-en un nouveau depuis l'application.",
)
EMAIL_UNAVAILABLE = ApiError(
    503, "email_unavailable", "L'e-mail n'a pas pu partir. Réessayez dans quelques minutes."
)


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterIn, request: Request, db: DbSession, settings: AppSettings, mailer: Mailer
) -> TokensOut:
    """Crée le compte et envoie « Confirmez votre adresse » ; si l'e-mail ne part pas, le compte
    est quand même créé et le parent pourra redemander le lien."""
    rate_limit(request, f"register:{client_ip(request)}", limit=10, window_s=3600)
    now = clock.now()
    try:
        parent = await accounts.register_parent(db, body.email, body.password, now, body.first_name)
    except accounts.EmailTaken as exc:
        raise ApiError(409, "email_taken", "Un compte existe déjà avec cet e-mail.") from exc
    pair = await accounts.issue_tokens(db, parent.id, settings, now)
    await accounts.send_email_verification(db, parent, settings, mailer, now)
    await db.commit()
    return tokens_out(pair, parent)


@router.post("/auth/login")
async def login(body: LoginIn, request: Request, db: DbSession, settings: AppSettings) -> TokensOut:
    ip = client_ip(request)
    rate_limit(request, f"login:{ip}:{accounts.normalize_email(body.email)}", limit=5, window_s=60)
    rate_limit(request, f"login-ip:{ip}", limit=30, window_s=60)
    now = clock.now()
    try:
        parent = await accounts.authenticate(db, body.email, body.password, now)
    except accounts.InvalidCredentials as exc:
        raise BAD_CREDENTIALS from exc
    pair = await accounts.issue_tokens(db, parent.id, settings, now)
    await db.commit()
    return tokens_out(pair, parent)


@router.post("/auth/refresh")
async def refresh(body: RefreshIn, db: DbSession, settings: AppSettings) -> TokensOut:
    try:
        pair = await accounts.rotate_refresh_token(db, body.refresh_token, settings, clock.now())
    except accounts.InvalidCredentials as exc:
        await db.commit()  # enregistre la révocation de la chaîne en cas de réutilisation
        raise ApiError(401, "invalid_token", "Session expirée, reconnectez-vous.") from exc
    await db.commit()
    parent_id = decode_access_token(pair.access_token, settings.jwt_secret.get_secret_value())
    parent = await db.get(Parent, parent_id)
    assert parent is not None
    return tokens_out(pair, parent)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshIn, db: DbSession) -> Response:
    await accounts.revoke_refresh_token(db, body.refresh_token, clock.now())
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/auth/password-reset", status_code=status.HTTP_202_ACCEPTED)
async def password_reset(
    body: PasswordResetIn, request: Request, db: DbSession, settings: AppSettings, mailer: Mailer
) -> dict[str, str]:
    """Répond toujours 202 : on ne révèle pas si l'e-mail a un compte."""
    rate_limit(request, f"reset:{accounts.normalize_email(body.email)}", limit=3, window_s=3600)
    rate_limit(request, f"reset-ip:{client_ip(request)}", limit=10, window_s=3600)
    try:
        await accounts.request_password_reset(db, body.email, settings, mailer, clock.now())
    except EmailNotSent as exc:
        await db.rollback()
        raise EMAIL_UNAVAILABLE from exc
    await db.commit()
    return {"status": "Si un compte existe pour cet e-mail, un lien a été envoyé."}


@router.post("/auth/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def password_reset_confirm(body: PasswordResetConfirmIn, db: DbSession) -> Response:
    try:
        await accounts.reset_password(db, body.token, body.new_password, clock.now())
    except accounts.InvalidCredentials as exc:
        raise ApiError(
            400, "invalid_reset_token", "Ce lien n'est plus valable. Refaites une demande."
        ) from exc
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/auth/verify-email")
async def verify_email(body: EmailVerificationIn, request: Request, db: DbSession) -> ParentOut:
    """Lien « Confirmer mon adresse » ouvert dans l'application (sans être connecté)."""
    rate_limit(request, f"verify-ip:{client_ip(request)}", limit=20, window_s=3600)
    try:
        parent = await accounts.verify_email(db, body.token, clock.now())
    except accounts.InvalidCredentials as exc:
        raise INVALID_VERIFICATION from exc
    await db.commit()
    return parent_out(parent)


@router.post("/parent/verify-email", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(
    parent: CurrentParent, request: Request, db: DbSession, settings: AppSettings, mailer: Mailer
) -> dict[str, str]:
    """Renvoie le lien de confirmation (3 fois par heure au plus)."""
    found = await db.get(Parent, parent.parent_id)
    assert found is not None
    if found.email_verified_at is not None:
        raise ApiError(409, "email_already_verified", "Votre adresse est déjà confirmée.")
    rate_limit(request, f"verify-resend:{found.id}", limit=3, window_s=3600)
    if not await accounts.send_email_verification(db, found, settings, mailer, clock.now()):
        await db.rollback()
        raise EMAIL_UNAVAILABLE
    await db.commit()
    return {"status": f"Un lien a été envoyé à {found.email}."}


@router.get("/parent")
async def me_parent(parent: CurrentParent, db: DbSession) -> ParentOut:
    found = await db.get(Parent, parent.parent_id)
    assert found is not None
    return parent_out(found)


@router.patch("/parent")
async def update_parent(body: ParentPatch, parent: CurrentParent, db: DbSession) -> ParentOut:
    found = await db.get(Parent, parent.parent_id)
    assert found is not None
    found.first_name = body.first_name
    await db.commit()
    return parent_out(found)


@router.delete("/parent", status_code=status.HTTP_204_NO_CONTENT)
async def delete_parent(parent: CurrentParent, db: DbSession) -> Response:
    """Droit à l'effacement : le compte, la famille, les enfants et toutes leurs données."""
    await accounts.delete_parent(db, parent.parent_id)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
