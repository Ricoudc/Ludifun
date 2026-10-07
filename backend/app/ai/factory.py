"""Choix du fournisseur d'IA : réglage du serveur (`LUDIFUN_AI_PROVIDER`), ou celui qu'une
famille a choisi dans l'espace parent (`AiChoice`, `app/services/ai_settings.py`).

- `ollama` : IA installée sur le PC (API native, gratuite) ;
- `claude` : adaptateur dédié (API Anthropic) ;
- `openai`, `gemini`, `mistral`, `groq`, `xai` : API compatibles OpenAI, adresse et modèles
  conseillés dans `app/ai/presets.py`, clé dans leur variable habituelle (`OPENAI_API_KEY`…) ;
- `compatible` : tout autre service compatible OpenAI (Azure OpenAI pour l'IA de Copilot,
  OpenRouter…) avec `LUDIFUN_AI_BASE_URL`, `LUDIFUN_AI_API_KEY` et `LUDIFUN_AI_MODEL` ;
- `fake` : réponses rejouées, sans clé.

Ajouter un fournisseur au format différent : une classe qui respecte `LLMProvider`
(`app/ai/ports.py`) dans `app/ai/providers/`, une entrée dans `build_llm` et dans
`app/ai/presets.py`, son nom dans `AiProviderName`. Le reste de l'application ne change pas.
"""

import logging
import os
from dataclasses import dataclass

import anthropic

from app.ai.ocr.vision_llm import VisionLLMOcr
from app.ai.ports import LLMProvider, OcrProvider, Stage
from app.ai.presets import PRESETS
from app.ai.providers.claude import ClaudeProvider
from app.ai.providers.fake import FakeProvider
from app.ai.providers.ollama import OllamaProvider
from app.ai.providers.openai_compatible import OpenAICompatibleProvider
from app.config import AiProviderName, Settings

logger = logging.getLogger("ludifun.ai")
STAGES: tuple[Stage, ...] = ("ocr", "analysis", "material", "evaluation", "sources", "illustration")


class AiConfigError(ValueError):
    """Réglage de l'IA incomplet (clé, adresse ou modèle manquant)."""


@dataclass(frozen=True)
class AiChoice:
    """L'IA choisie par une famille ; ce qui manque vient du réglage du serveur."""

    provider: AiProviderName
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None


def stage_models(settings: Settings, model: str | None = None) -> dict[Stage, str]:
    """Modèle de chaque étape : le modèle choisi, sinon le réglage de l'étape, puis
    `LUDIFUN_AI_MODEL`, puis le modèle conseillé du fournisseur."""
    preset = PRESETS[settings.ai_provider]
    chosen: dict[Stage, str | None] = {
        "ocr": settings.ai_ocr_model,
        "analysis": settings.ai_analysis_model,
        "material": settings.ai_material_model,
        "evaluation": settings.ai_evaluation_model,
        "sources": settings.ai_analysis_model,  # lire des extraits et expliquer : le modèle principal
        "illustration": settings.ai_evaluation_model,  # une scène en une phrase : le modèle rapide
    }
    models: dict[Stage, str] = {}
    for stage in STAGES:
        found = model or chosen[stage] or settings.ai_model or preset.models.get(stage)
        if not found:
            raise AiConfigError("modèle manquant : indiquez le modèle à utiliser chez ce fournisseur")
        models[stage] = found
    return models


def _key(settings: Settings, given: str | None) -> str:
    if given is not None:
        return given
    preset = PRESETS[settings.ai_provider]
    if settings.ai_provider == "compatible" and settings.ai_api_key is not None:
        return settings.ai_api_key.get_secret_value()
    key = os.environ.get(preset.key_env, "") if preset.key_env else ""
    if not key and preset.key_env:
        logger.warning("%s absente : les analyses de leçons échoueront (voir .env).", preset.key_env)
    return key


def build_llm(settings: Settings, choice: AiChoice | None = None) -> LLMProvider:
    if choice is not None:
        update: dict[str, object] = {"ai_provider": choice.provider, "ai_base_url": choice.base_url or None}
        if choice.provider != settings.ai_provider:
            # Les modèles du .env valent pour l'IA du serveur, pas pour celle choisie par la
            # famille chez un autre fournisseur (« gemini-2.5-pro » envoyé à Ollama).
            update |= dict.fromkeys(
                ("ai_model", "ai_ocr_model", "ai_analysis_model", "ai_material_model", "ai_evaluation_model")
            )
        settings = settings.model_copy(update=update)
    model = choice.model if choice else None
    api_key = choice.api_key if choice else None
    provider = settings.ai_provider
    if provider == "fake":
        return FakeProvider()
    models = stage_models(settings, model)
    if provider == "ollama":
        return OllamaProvider(
            settings.ai_base_url or settings.ollama_base_url, models, settings.ollama_num_ctx
        )
    if provider == "claude":
        key = _key(settings, api_key)
        client = anthropic.AsyncAnthropic(api_key=key) if api_key else None
        return ClaudeProvider(
            models=models,
            efforts={
                "ocr": settings.ai_ocr_effort,
                "analysis": settings.ai_analysis_effort,
                "material": settings.ai_material_effort,
                "evaluation": settings.ai_evaluation_effort,
                "sources": settings.ai_material_effort,
                "illustration": settings.ai_evaluation_effort,
            },
            client=client,
        )
    base_url = settings.ai_base_url or PRESETS[provider].base_url
    if not base_url:
        raise AiConfigError("adresse manquante : l'adresse de l'API compatible OpenAI (LUDIFUN_AI_BASE_URL)")
    return OpenAICompatibleProvider(provider, base_url, _key(settings, api_key), models)


def build_providers(settings: Settings, choice: AiChoice | None = None) -> tuple[OcrProvider, LLMProvider]:
    """Fournisseurs configurés : la lecture des photos utilise le même modèle multimodal (§5.1)."""
    llm = build_llm(settings, choice)
    return VisionLLMOcr(llm), llm
