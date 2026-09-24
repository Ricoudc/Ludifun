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
    key_url: str = ""  # où créer la clé
    note: str = ""  # affiché au parent au moment du choix

    def model(self, stage: Stage) -> str:
        return self.models[stage]


def _same(main: str, fast: str) -> dict[Stage, str]:
    """Le modèle principal lit et analyse ; le rapide corrige les réponses pendant la séance."""
    return {"ocr": main, "analysis": main, "material": main, "evaluation": fast}


# Modèle local conseillé : lit bien les photos de cahier (vision) et tient sur un PC récent.
OLLAMA_MODEL = "qwen2.5vl:7b"

PRESETS: dict[str, Preset] = {
    # Ollama : IA installée sur le PC (gratuite, rien ne sort de la maison). Adresse : réglage
    # LUDIFUN_OLLAMA_BASE_URL (ou celle choisie par le parent).
    "ollama": Preset(
        "Ollama (sur ce PC)",
        "",
        None,
        _same(OLLAMA_MODEL, OLLAMA_MODEL),
        "https://ollama.com/download",
        "Gratuite, rien ne sort de la maison. Le modèle doit savoir lire les images "
        f"(« ollama pull {OLLAMA_MODEL} »). Plus lente sans carte graphique.",
    ),
    "claude": Preset(
        "Claude (Anthropic)",
        "ANTHROPIC_API_KEY",
        None,
        _same("claude-opus-5", "claude-sonnet-5"),
        "https://console.anthropic.com",
        "La référence de Ludifun : les consignes ont été mises au point avec Claude. Payant à l'usage.",
    ),
    "openai": Preset(
        "ChatGPT (OpenAI)",
        "OPENAI_API_KEY",
        "https://api.openai.com/v1",
        _same("gpt-5", "gpt-5-mini"),
        "https://platform.openai.com/api-keys",
        "Payant à l'usage.",
    ),
    "gemini": Preset(
        "Gemini (Google)",
        "GEMINI_API_KEY",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        _same("gemini-2.5-pro", "gemini-2.5-flash"),
        "https://aistudio.google.com/apikey",
        "L'offre gratuite peut réutiliser les données envoyées : pour des leçons d'enfants, activez "
        "la facturation.",
    ),
    "mistral": Preset(
        "Mistral",
        "MISTRAL_API_KEY",
        "https://api.mistral.ai/v1",
        _same("mistral-medium-latest", "mistral-small-latest"),
        "https://console.mistral.ai/api-keys",
        "Entreprise française, serveurs en Europe. Payant à l'usage.",
    ),
    "groq": Preset(
        "Groq",
        "GROQ_API_KEY",
        "https://api.groq.com/openai/v1",
        _same("meta-llama/llama-4-maverick-17b-128e-instruct", "openai/gpt-oss-120b"),
        "https://console.groq.com/keys",
        "Très rapide. Payant à l'usage, avec une offre gratuite limitée.",
    ),
    "xai": Preset(
        "Grok (xAI)",
        "XAI_API_KEY",
        "https://api.x.ai/v1",
        _same("grok-4", "grok-4"),
        "https://console.x.ai",
        "Payant à l'usage.",
    ),
    # Tout service qui parle comme l'API OpenAI : Azure OpenAI (l'IA de Copilot), OpenRouter…
    "compatible": Preset(
        "Autre service (Copilot / Azure OpenAI, OpenRouter…)",
        "LUDIFUN_AI_API_KEY",
        None,
        {},
        "",
        "Copilot n'a pas d'API : ses modèles s'utilisent par Azure OpenAI. Indiquez l'adresse de "
        "l'API (souvent terminée par /v1), la clé et le modèle.",
    ),
}
