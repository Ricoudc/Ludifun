"""Compte parent : inscription, connexion, jetons, mot de passe, suppression."""

from fastapi import APIRouter, Request, Response, status

from app import clock
from app.api.deps import AppSettings, CurrentParent, DbSession, Mailer, client_ip, rate_limit
from app.api.errors import ApiError
from app.api.v1.schemas import (
    LoginIn,
    ParentOut,
    PasswordResetConfirmIn,
    PasswordResetIn,
    RefreshIn,
    RegisterIn,
    TokensOut,
)
from app.db.models import Parent
from app.security.tokens import decode_access_token
from app.services import accounts

router = APIRouter(tags=["compte parent"])

BAD_CREDENTIALS = ApiError(401, "invalid_credentials", "E-mail ou mot de passe incorrect.")


def tokens_out(pair: accounts.TokenPair, parent: Parent) -> TokensOut:
    return TokensOut(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.expires_in,
        parent=ParentOut(id=parent.id, email=parent.email),
    )


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn, request: Request, db: DbSession, settings: AppSettings) -> TokensOut:
    rate_limit(request, f"register:{client_ip(request)}", limit=10, window_s=3600)
    now = clock.now()
    try:
        parent = await accounts.register_parent(db, body.email, body.password, now)
    except accounts.EmailTaken as exc:
        raise ApiError(409, "email_taken", "Un compte existe déjà avec cet e-mail.") from exc
    pair = await accounts.issue_tokens(db, parent.id, settings, now)
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
    await accounts.request_password_reset(db, body.email, settings, mailer, clock.now())
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


@router.get("/parent")
async def me_parent(parent: CurrentParent, db: DbSession) -> ParentOut:
    found = await db.get(Parent, parent.parent_id)
    assert found is not None
    return ParentOut(id=found.id, email=found.email)


@router.delete("/parent", status_code=status.HTTP_204_NO_CONTENT)
async def delete_parent(parent: CurrentParent, db: DbSession) -> Response:
    """Droit à l'effacement : le compte, la famille, les enfants et toutes leurs données."""
    await accounts.delete_parent(db, parent.parent_id)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
