"""Espace parent : l'IA qui lit les photos et crée les jeux de la famille."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import select

from app import clock
from app.ai.check import check, probe_llm
from app.ai.factory import AiChoice, AiConfigError
from app.ai.ports import AIError
from app.ai.presets import PRESETS
from app.api.deps import AppSettings, CurrentParent, DbSession, get_ai_resolver, rate_limit
from app.api.errors import ApiError
from app.config import AiProviderName, Settings
from app.db.models import Family
from app.services import ai_settings
from app.services.ai_settings import AiResolver

router = APIRouter(tags=["compte parent"])

Resolver = Annotated[AiResolver, Depends(get_ai_resolver)]
Url = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300, pattern=r"^https?://\S+$")]
Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
CUSTOM_URL = ("ollama", "compatible")
ORDER: tuple[AiProviderName, ...] = (
    "ollama", "claude", "openai", "gemini", "mistral", "groq", "xai", "compatible", "fake"
)  # fmt: skip


class ProviderOut(BaseModel):
    code: AiProviderName
    label: str
    note: str
    needs_key: bool
    custom_url: bool = Field(description="Adresse de l'API à indiquer (Ollama, service compatible).")
    default_url: str | None
    default_model: str | None
    key_url: str
    recommended: bool
    available: bool = Field(description="Faux : refusé par ce serveur (adresse libre en production).")


class FamilyAiOut(BaseModel):
    provider: AiProviderName
    model: str | None
    base_url: str | None
    key_hint: str | None = Field(description="Fin de la clé enregistrée (« …a1b2 ») ; jamais la clé.")


class AiSettingsOut(BaseModel):
    family: FamilyAiOut | None = Field(description="IA active ; null : la famille utilise celle du serveur.")
    saved: list[FamilyAiOut] = Field(
        description="Toutes les IA déjà réglées (chacune garde sa clé), pour passer de l'une à l'autre."
    )
    server_provider: str = Field(description="IA du serveur, utilisée sans choix de la famille.")
    fallback: bool = Field(
        False,
        description="Si l'IA active ne répond pas, essayer les autres IA enregistrées par la famille (§147).",
    )
    providers: list[ProviderOut]
    web_sources: bool = Field(
        False, description="Recherche sur des sites éducatifs autorisés (étape 24), permise par le parent."
    )
    web_sources_available: bool = Field(
        False, description="Le serveur a un moteur de recherche (LUDIFUN_WEB_SEARCH_URL)."
    )


class WebSourcesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class AiSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: AiProviderName
    model: Short | None = None
    base_url: Url | None = None
    api_key: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = Field(
        None, description="null : garder la clé déjà enregistrée pour cette IA."
    )
    fallback: bool | None = Field(
        None, description="Repli sur les autres IA de la famille ; null : inchangé."
    )


class CheckOut(BaseModel):
    ok: bool
    message: str
    models: list[str]


def providers_out(settings: Settings) -> list[ProviderOut]:
    out = []
    for code in ORDER:
        if code == "fake":
            out.append(
                ProviderOut(
                    code="fake",
                    label="Démonstration (sans IA)",
                    note="Gratuite : toute photo devient une leçon d'exemple. Pour découvrir l'application.",
                    needs_key=False,
                    custom_url=False,
                    default_url=None,
                    default_model=None,
                    key_url="",
                    recommended=False,
                    available=True,
                )
            )
            continue
        preset = PRESETS[code]
        custom = code in CUSTOM_URL
        out.append(
            ProviderOut(
                code=code,
                label=preset.label,
                note=preset.note,
                needs_key=bool(preset.key_env) and code != "compatible",
                custom_url=custom,
                default_url=settings.ollama_base_url if code == "ollama" else None,
                default_model=preset.models.get("ocr"),
                key_url=preset.key_url,
                recommended=code == "ollama",
                available=settings.custom_ai_url_allowed or not custom,
            )
        )
    return out


async def _family(db: DbSession, parent: CurrentParent) -> uuid.UUID:
    family_id = await ai_settings.family_of_parent(db, parent.parent_id)
    if family_id is None:
        raise ApiError(404, "family_not_found", "Famille introuvable.")
    return family_id


async def settings_out(
    db: DbSession, family_id: uuid.UUID, settings: Settings, resolver: Resolver
) -> AiSettingsOut:
    active = await ai_settings.load(db, family_id)
    rows = await ai_settings.load_providers(db, family_id)
    saved = {
        name: FamilyAiOut(
            provider=row.provider,  # contrainte en base : un nom connu
            model=row.model,
            base_url=row.base_url,
            key_hint=row.key_hint,
        )
        for name, row in rows.items()
    }
    family = None
    if active is not None:
        family = saved.get(active.provider) or FamilyAiOut(
            provider=active.provider, model=None, base_url=None, key_hint=None
        )
    return AiSettingsOut(
        family=family,
        saved=[saved[code] for code in ORDER if code in saved],
        server_provider=resolver.default[1].name,
        fallback=active.fallback if active is not None else False,
        providers=providers_out(settings),
        web_sources=bool(await db.scalar(select(Family.web_sources).where(Family.id == family_id))),
        web_sources_available=bool(settings.web_search_url),
    )


async def _choice(
    db: DbSession, family_id: uuid.UUID, body: AiSettingsIn, settings: Settings
) -> tuple[AiChoice, bool]:
    """Le choix complété (adresse par défaut, clé enregistrée) ; vrai si la clé enregistrée est gardée."""
    if body.provider in CUSTOM_URL and not settings.custom_ai_url_allowed:
        raise ApiError(403, "ai_provider_not_allowed", "Ce serveur n'autorise pas d'adresse d'IA libre.")
    base_url = body.base_url
    if body.provider == "ollama" and not base_url:
        base_url = settings.ollama_base_url
    if body.provider == "compatible" and not base_url:
        raise ApiError(422, "base_url_required", "Indiquez l'adresse de l'API (souvent terminée par /v1).")
    if body.provider not in CUSTOM_URL:
        base_url = None
    row = (await ai_settings.load_providers(db, family_id)).get(body.provider)
    keep = body.api_key is None and row is not None
    key = body.api_key or None
    if keep and row is not None and row.api_key_encrypted:
        key = ai_settings.decrypt(settings, row.api_key_encrypted)
    needs_key = body.provider not in ("ollama", "compatible", "fake")
    if needs_key and not key:
        raise ApiError(422, "api_key_required", f"Collez la clé d'API de {PRESETS[body.provider].label}.")
    return AiChoice(body.provider, body.model, base_url, key), keep


@router.get("/parent/ai")
async def get_ai_settings(
    parent: CurrentParent, db: DbSession, settings: AppSettings, resolver: Resolver
) -> AiSettingsOut:
    return await settings_out(db, await _family(db, parent), settings, resolver)


@router.put("/parent/ai")
async def put_ai_settings(
    body: AiSettingsIn, parent: CurrentParent, db: DbSession, settings: AppSettings, resolver: Resolver
) -> AiSettingsOut:
    """Choisit l'IA de la famille ; elle sert dès la prochaine leçon."""
    family_id = await _family(db, parent)
    choice, keep = await _choice(db, family_id, body, settings)
    try:
        resolver.for_choice(choice)
    except AiConfigError as exc:
        raise ApiError(422, "ai_not_configured", str(exc).capitalize() + ".") from exc
    await ai_settings.save(
        db, family_id, settings, choice, clock.now(), keep_key=keep, fallback=body.fallback
    )
    await db.commit()
    return await settings_out(db, family_id, settings, resolver)


@router.put("/parent/ai/sources")
async def put_web_sources(
    body: WebSourcesIn, parent: CurrentParent, db: DbSession, settings: AppSettings, resolver: Resolver
) -> AiSettingsOut:
    """Autorise (ou non) la recherche sur des sites éducatifs pour aider l'enfant (étape 24).
    Seule la notion part sur Internet, jamais le prénom de l'enfant ni sa photo."""
    family_id = await _family(db, parent)
    if body.enabled and not settings.web_search_url:
        raise ApiError(
            409,
            "web_search_unavailable",
            "Ce serveur n'a pas de moteur de recherche (LUDIFUN_WEB_SEARCH_URL).",
        )
    family = await db.get(Family, family_id)
    assert family is not None
    family.web_sources = body.enabled
    await db.commit()
    return await settings_out(db, family_id, settings, resolver)


@router.delete("/parent/ai", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ai_settings(parent: CurrentParent, db: DbSession) -> Response:
    """Revenir à l'IA du serveur. Les clés enregistrées restent, pour y revenir plus tard."""
    row = await ai_settings.load(db, await _family(db, parent))
    if row is not None:
        await db.delete(row)
        await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/parent/ai/providers/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def forget_ai_provider(provider: AiProviderName, parent: CurrentParent, db: DbSession) -> Response:
    """Oublier une IA : sa clé est effacée. Si c'était l'IA active, retour à celle du serveur."""
    if not await ai_settings.forget(db, await _family(db, parent), provider):
        raise ApiError(404, "ai_provider_not_saved", "Aucun réglage enregistré pour cette IA.")
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/parent/ai/test")
async def test_ai_settings(
    body: AiSettingsIn,
    request: Request,
    parent: CurrentParent,
    db: DbSession,
    settings: AppSettings,
    resolver: Resolver,
) -> CheckOut:
    """Vérifier l'IA : le service répond, la clé est acceptée, le modèle est là (et lit les images
    avec Ollama), puis une petite demande d'essai. Liste aussi les modèles."""
    rate_limit(request, f"ai-test:{parent.parent_id}", limit=30, window_s=3600)
    family_id = await _family(db, parent)
    choice, _ = await _choice(db, family_id, body, settings)

    async def probe(tested: AiChoice) -> None:
        try:
            _, llm = resolver.for_choice(tested)
        except AiConfigError as exc:
            raise AIError(str(exc)) from exc
        await probe_llm(llm)

    result = await check(choice, settings, getattr(request.app.state, "ai_check_client", None), probe)
    return CheckOut(ok=result.ok, message=result.message, models=result.models)
