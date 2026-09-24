"""Choix du fournisseur d'IA (`LUDIFUN_AI_PROVIDER`).

Ajouter un fournisseur (autre modèle, autre clé d'API) : une classe qui respecte `LLMProvider`
(`app/ai/ports.py` : sorties structurées selon un schéma, images pour la lecture des photos)
dans `app/ai/providers/`, une entrée dans `PROVIDERS`, et son nom dans `Settings.ai_provider`.
Le reste de l'application (pipeline, correction des réponses, journal des coûts) ne change pas.
Voir « Fournisseurs d'IA » dans `backend/README.md`.
"""

import logging
import os
from collections.abc import Callable

from app.ai.ocr.vision_llm import VisionLLMOcr
from app.ai.ports import LLMProvider, OcrProvider
from app.ai.providers.claude import ClaudeProvider
from app.ai.providers.fake import FakeProvider
from app.config import Settings

logger = logging.getLogger("ludifun.ai")


def _claude(settings: Settings) -> LLMProvider:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.warning("ANTHROPIC_API_KEY absente : les analyses de leçons échoueront (voir .env).")
    return ClaudeProvider(
        models={
            "ocr": settings.ai_ocr_model,
            "analysis": settings.ai_analysis_model,
            "material": settings.ai_material_model,
            "evaluation": settings.ai_evaluation_model,
        },
        efforts={
            "ocr": settings.ai_ocr_effort,
            "analysis": settings.ai_analysis_effort,
            "material": settings.ai_material_effort,
            "evaluation": settings.ai_evaluation_effort,
        },
    )


def _fake(_: Settings) -> LLMProvider:
    return FakeProvider()


PROVIDERS: dict[str, Callable[[Settings], LLMProvider]] = {"claude": _claude, "fake": _fake}


def build_providers(settings: Settings) -> tuple[OcrProvider, LLMProvider]:
    """Fournisseurs configurés : la lecture des photos utilise le même modèle multimodal (§5.1)."""
    llm = PROVIDERS[settings.ai_provider](settings)
    return VisionLLMOcr(llm), llm
