"""Relève l'état de l'installation pour le parent (§5.89) : l'IA de la famille répond-elle, sa
clé est-elle lisible, le modèle tient-il dans la carte graphique, les dernières leçons ont-elles
abouti, le plafond du jour est-il atteint, des leçons attendent-elles sa relecture ?

Aucun appel payant : le service d'IA est seulement interrogé sur sa présence et ses modèles.
"""

import uuid
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.check import check
from app.ai.factory import AiChoice, stage_models
from app.config import Settings
from app.db import models as db
from app.domain.installation import Check, Level, OllamaModel, gpu_check, lessons_check
from app.services import ai_budget, ai_settings

OLLAMA_TIMEOUT_S = 5.0


async def _ollama_models(base_url: str, client: httpx.AsyncClient, path: str) -> list[OllamaModel]:
    try:
        response = await client.get(f"{base_url.rstrip('/')}{path}", timeout=OLLAMA_TIMEOUT_S)
        rows: list[Any] = response.json().get("models", [])
    except (httpx.HTTPError, ValueError, AttributeError):
        return []
    found = []
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("name") or row.get("model"), str):
            vram = row.get("size_vram")
            found.append(
                OllamaModel(
                    name=row.get("name") or row["model"],
                    size=int(row.get("size") or 0),
                    size_vram=int(vram) if isinstance(vram, int) else None,
                )
            )
    return found


async def _ai_checks(
    session: AsyncSession, family_id: uuid.UUID, settings: Settings, client: httpx.AsyncClient
) -> list[Check]:
    active = await ai_settings.load(session, family_id)
    rows = await ai_settings.load_providers(session, family_id)
    row = rows.get(active.provider) if active is not None else None
    if row is not None and ai_settings.key_lost(settings, row.api_key_encrypted):
        return [
            Check(
                "ai",
                Level.ERROR,
                "Intelligence artificielle",
                "La clé de votre IA n'est plus lisible (Ludifun a sans doute été réinstallé ou "
                "lancé depuis un autre dossier) : les leçons ne peuvent pas être préparées avec elle.",
                "Mon compte → Intelligence artificielle : collez de nouveau la clé.",
            )
        ]
    if active is None:
        choice = AiChoice(settings.ai_provider)
        whose = "l'IA du serveur"
    else:
        choice = ai_settings.choice_of(row, settings) if row else AiChoice(active.provider)  # type: ignore[arg-type]
        whose = "votre IA"
    result = await check(choice, settings, client)
    checks = [
        Check(
            "ai",
            Level.OK if result.ok else Level.ERROR,
            "Intelligence artificielle",
            f"Ludifun utilise {whose} ({choice.provider}). {result.message}",
            None
            if result.ok
            else "Mon compte → Intelligence artificielle : vérifiez le réglage, puis « Tester ».",
        )
    ]
    if choice.provider == "ollama" and result.ok:
        base_url = choice.base_url or settings.ollama_base_url
        model = choice.model or stage_models(settings.model_copy(update={"ai_provider": "ollama"}))["ocr"]
        loaded = await _ollama_models(base_url, client, "/api/ps")
        installed = await _ollama_models(base_url, client, "/api/tags")
        checks.append(gpu_check(model, loaded, installed))
    if (
        active is not None
        and not active.fallback
        and choice.provider == "ollama"
        and any(name != active.provider for name in rows)
    ):
        checks.append(
            Check(
                "fallback",
                Level.WARNING,
                "IA de secours",
                "Vous avez réglé une autre IA, mais elle ne prend pas le relais quand Ollama échoue.",
                "Mon compte → Intelligence artificielle : cochez l'IA de secours si vous le souhaitez.",
            )
        )
    return checks


async def report(
    session: AsyncSession, family_id: uuid.UUID, settings: Settings, client: httpx.AsyncClient, now: datetime
) -> list[Check]:
    checks = await _ai_checks(session, family_id, settings, client)

    children = select(db.Child.id).where(db.Child.family_id == family_id)
    statuses = list(
        await session.scalars(
            select(db.Lesson.status)
            .where(db.Lesson.child_id.in_(children), db.Lesson.status.in_(("ready", "failed")))
            .order_by(db.Lesson.created_at.desc())
            .limit(10)
        )
    )
    checks.append(lessons_check(statuses))

    wait = await ai_budget.seconds_until_budget(session, settings.ai_daily_budget_usd, now)
    checks.append(
        Check("budget", Level.OK, "Plafond de dépense du jour", "Le plafond du jour n'est pas atteint.")
        if wait is None
        else Check(
            "budget",
            Level.WARNING,
            "Plafond de dépense du jour",
            "Le plafond de dépense d'IA du jour est atteint : les nouvelles leçons attendront demain.",
            "Réglage LUDIFUN_AI_DAILY_BUDGET_USD du serveur.",
        )
    )

    if await session.scalar(select(db.Family.review_lessons).where(db.Family.id == family_id)):
        waiting = await session.scalar(
            select(func.count())
            .select_from(db.Lesson)
            .where(
                db.Lesson.child_id.in_(children),
                db.Lesson.status == "ready",
                db.Lesson.parent_approved_at.is_(None),
            )
        )
        if waiting:
            checks.append(
                Check(
                    "review",
                    Level.WARNING,
                    "Leçons à relire",
                    f"{waiting} leçon(s) attendent votre relecture : l'enfant n'y a pas encore accès.",
                    "Tableau de bord de l'enfant → ouvrez la leçon, relisez-la, puis validez-la.",
                )
            )
    return checks
