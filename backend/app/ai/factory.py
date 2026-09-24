"""Choix du fournisseur d'IA (`LUDIFUN_AI_PROVIDER`).

- `claude` : adaptateur dédié (API Anthropic) ;
- `openai`, `gemini`, `mistral`, `groq`, `xai` : API compatibles OpenAI, adresse et modèles
  conseillés dans `app/ai/presets.py`, clé dans leur variable habituelle (`OPENAI_API_KEY`…) ;
- `compatible` : tout autre service compatible OpenAI (Azure OpenAI pour l'IA de Copilot,
  OpenRouter, Ollama…) avec `LUDIFUN_AI_BASE_URL`, `LUDIFUN_AI_API_KEY` et `LUDIFUN_AI_MODEL` ;
- `fake` : réponses rejouées, sans clé.

Ajouter un fournisseur au format différent : une classe qui respecte `LLMProvider`
(`app/ai/ports.py`) dans `app/ai/providers/`, et une entrée dans `build_llm`. Le reste de
l'application (pipeline, correction des réponses, journal des coûts) ne change pas.
"""

import logging
import os

from app.ai.ocr.vision_llm import VisionLLMOcr
from app.ai.ports import LLMProvider, OcrProvider, Stage
from app.ai.presets import PRESETS
from app.ai.providers.claude import ClaudeProvider
from app.ai.providers.fake import FakeProvider
from app.ai.providers.openai_compatible import OpenAICompatibleProvider
from app.config import Settings

logger = logging.getLogger("ludifun.ai")
STAGES: tuple[Stage, ...] = ("ocr", "analysis", "material", "evaluation")


class AiConfigError(ValueError):
    """Réglage de l'IA incomplet (clé, adresse ou modèle manquant)."""


def stage_models(settings: Settings) -> dict[Stage, str]:
    """Modèle de chaque étape : réglage de l'étape, puis `LUDIFUN_AI_MODEL`, puis le conseillé."""
    preset = PRESETS[settings.ai_provider]
    chosen: dict[Stage, str | None] = {
        "ocr": settings.ai_ocr_model,
        "analysis": settings.ai_analysis_model,
        "material": settings.ai_material_model,
        "evaluation": settings.ai_evaluation_model,
    }
    models: dict[Stage, str] = {}
    for stage in STAGES:
        model = chosen[stage] or settings.ai_model or preset.models.get(stage)
        if not model:
            raise AiConfigError("LUDIFUN_AI_MODEL manque : le modèle à utiliser chez ce fournisseur")
        models[stage] = model
    return models


def _key(settings: Settings) -> str:
    preset = PRESETS[settings.ai_provider]
    if settings.ai_provider == "compatible" and settings.ai_api_key is not None:
        return settings.ai_api_key.get_secret_value()
    key = os.environ.get(preset.key_env, "")
    if not key:
        logger.warning("%s absente : les analyses de leçons échoueront (voir .env).", preset.key_env)
    return key


def build_llm(settings: Settings) -> LLMProvider:
    if settings.ai_provider == "fake":
        return FakeProvider()
    models = stage_models(settings)
    if settings.ai_provider == "claude":
        _key(settings)  # le client Anthropic lit la clé lui-même ; on prévient seulement
        return ClaudeProvider(
            models=models,
            efforts={
                "ocr": settings.ai_ocr_effort,
                "analysis": settings.ai_analysis_effort,
                "material": settings.ai_material_effort,
                "evaluation": settings.ai_evaluation_effort,
            },
        )
    base_url = settings.ai_base_url or PRESETS[settings.ai_provider].base_url
    if not base_url:
        raise AiConfigError("LUDIFUN_AI_BASE_URL manque : l'adresse de l'API compatible OpenAI")
    return OpenAICompatibleProvider(settings.ai_provider, base_url, _key(settings), models)


def build_providers(settings: Settings) -> tuple[OcrProvider, LLMProvider]:
    """Fournisseurs configurés : la lecture des photos utilise le même modèle multimodal (§5.1)."""
    llm = build_llm(settings)
    return VisionLLMOcr(llm), llm
