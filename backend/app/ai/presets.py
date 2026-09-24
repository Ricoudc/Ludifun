"""Fournisseurs d'IA connus : adresse de l'API, variable de la clé, modèles conseillés.

Les modèles se changent sans toucher au code (`LUDIFUN_AI_MODEL` pour toutes les étapes, ou
`LUDIFUN_AI_OCR_MODEL`… étape par étape) : les noms évoluent vite chez chaque fournisseur. Les
prompts ont été mis au point avec Claude : mesurer un autre fournisseur avec
`app.tools.evaluate` avant de s'y fier (eval/README.md).
"""

from dataclasses import dataclass

from app.ai.ports import Stage


@dataclass(frozen=True)
class Preset:
    label: str
    key_env: str  # variable d'environnement de la clé
    base_url: str | None  # API compatible OpenAI (None : adaptateur dédié, ou adresse à fournir)
    models: dict[Stage, str]

    def model(self, stage: Stage) -> str:
        return self.models[stage]


def _same(main: str, fast: str) -> dict[Stage, str]:
    """Le modèle principal lit et analyse ; le rapide corrige les réponses pendant la séance."""
    return {"ocr": main, "analysis": main, "material": main, "evaluation": fast}


PRESETS: dict[str, Preset] = {
    "claude": Preset(
        "Claude (Anthropic)", "ANTHROPIC_API_KEY", None, _same("claude-opus-5", "claude-sonnet-5")
    ),
    "openai": Preset(
        "ChatGPT (OpenAI)", "OPENAI_API_KEY", "https://api.openai.com/v1", _same("gpt-5", "gpt-5-mini")
    ),
    "gemini": Preset(
        "Gemini (Google)",
        "GEMINI_API_KEY",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        _same("gemini-2.5-pro", "gemini-2.5-flash"),
    ),
    "mistral": Preset(
        "Mistral",
        "MISTRAL_API_KEY",
        "https://api.mistral.ai/v1",
        _same("mistral-medium-latest", "mistral-small-latest"),
    ),
    "groq": Preset(
        "Groq",
        "GROQ_API_KEY",
        "https://api.groq.com/openai/v1",
        _same("meta-llama/llama-4-maverick-17b-128e-instruct", "openai/gpt-oss-120b"),
    ),
    "xai": Preset("Grok (xAI)", "XAI_API_KEY", "https://api.x.ai/v1", _same("grok-4", "grok-4")),
    # Tout service qui parle comme l'API OpenAI : Azure OpenAI (l'IA de Copilot), OpenRouter, Ollama…
    "compatible": Preset("Service compatible OpenAI", "LUDIFUN_AI_API_KEY", None, {}),
}
