"""Pages web publiques de l'API (étape 19) : confirmation de l'e-mail depuis n'importe quel
appareil, politique de confidentialité et suppression du compte (exigées par le Play Store).

HTML statique, sans script ni ressource externe ; aucune donnée personnelle affichée.
"""

import html
from importlib import resources
from typing import Annotated

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse

from app import clock
from app.api.deps import AppSettings, DbSession, client_ip, rate_limit
from app.api.errors import ApiError
from app.config import Settings
from app.services import accounts

router = APIRouter(tags=["pages web"], include_in_schema=False)

HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
    "frame-ancestors 'none'; base-uri 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}
STYLE = (
    "body{font-family:system-ui,sans-serif;max-width:42rem;margin:2rem auto;padding:0 1rem;"
    "line-height:1.55;color:#1f2330}h1{color:#6c4cf5}button{font-size:1.1rem;padding:.7rem 1.4rem;"
    "border:0;border-radius:.6rem;background:#6c4cf5;color:#fff;cursor:pointer}"
    "table{border-collapse:collapse}td,th{border:1px solid #ccd;padding:.3rem .5rem;text-align:left}"
)


def page(title: str, body: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)} · Ludifun</title><style>{STYLE}</style></head>"
        f"<body>{body}</body></html>",
        status_code=status_code,
        headers=HEADERS,
    )


def document(name: str, settings: Settings) -> str:
    text = resources.files("app.web").joinpath(name).read_text(encoding="utf-8")
    for key, value in {
        "legal_entity": settings.legal_entity,
        "contact_email": settings.contact_email,
        "hosting_provider": settings.hosting_provider,
        "email_provider": settings.email_provider,
        "updated": settings.privacy_updated,
    }.items():
        text = text.replace("{{" + key + "}}", html.escape(value))
    return text


@router.get("/verifier-email")
async def verification_form(jeton: Annotated[str, Query(max_length=200)] = "") -> HTMLResponse:
    """Le lien de l'e-mail n'agit pas tout seul (les antivirus ouvrent les liens) : un bouton."""
    return page(
        "Confirmer mon adresse",
        "<h1>Confirmer mon adresse</h1><p>Un clic pour confirmer que cette adresse e-mail est "
        "bien celle de votre compte Ludifun.</p><form method='post' action='/verifier-email'>"
        f"<input type='hidden' name='jeton' value='{html.escape(jeton, quote=True)}'>"
        "<button type='submit'>Confirmer</button></form>",
    )


@router.post("/verifier-email")
async def verification_submit(
    request: Request, db: DbSession, jeton: Annotated[str, Form(max_length=200)] = ""
) -> HTMLResponse:
    try:
        rate_limit(request, f"verify-ip:{client_ip(request)}", limit=20, window_s=3600)
        await accounts.verify_email(db, jeton, clock.now())
    except (accounts.InvalidCredentials, ApiError):
        return page(
            "Lien expiré",
            "<h1>Ce lien n'est plus valable</h1><p>Ouvrez l'application Ludifun, espace parent : "
            "« Renvoyer le lien » envoie un nouvel e-mail.</p>",
            status_code=400,
        )
    await db.commit()
    return page(
        "Adresse confirmée",
        "<h1>Adresse confirmée ✅</h1><p>Merci ! Vous pouvez fermer cette page et revenir dans "
        "l'application.</p>",
    )


@router.get("/confidentialite")
async def privacy_policy(settings: AppSettings) -> HTMLResponse:
    return page("Politique de confidentialité", document("confidentialite.html", settings))


@router.get("/suppression-compte")
async def account_deletion(settings: AppSettings) -> HTMLResponse:
    return page("Supprimer son compte", document("suppression-compte.html", settings))
