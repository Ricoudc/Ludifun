"""Prix des modèles (dollars par million de jetons, entrée / sortie) : évaluation et plafond
journalier (§16.1). Tarifs de l'API Anthropic ; pour les autres fournisseurs, modèles conseillés
(app/ai/presets.py) à des prix arrondis à la hausse. À tenir à jour avec les grilles publiques."""

# L'ordre compte : le préfixe le plus long d'abord (claude-opus-5-5 avant claude-opus-5).
PRICES_PER_MTOK = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-fable-5": (10.0, 50.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
    # Autres fournisseurs (prudents : la dépense réelle est plus basse).
    "gpt-5-mini": (0.5, 4.0),
    "gpt-5": (2.0, 15.0),
    "gemini-2.5-flash": (0.5, 4.0),
    "gemini-2.5-pro": (2.5, 15.0),
    "mistral-small": (0.5, 1.0),
    "mistral-medium": (1.0, 5.0),
    "meta-llama/llama-4": (0.5, 1.0),
    "openai/gpt-oss": (0.5, 1.0),
    "grok-4": (3.0, 15.0),
    "fake": (0.0, 0.0),
    "ollama/": (0.0, 0.0),  # IA locale : gratuite
}

# Modèle inconnu : on compte au prix le plus élevé, pour ne jamais sous-estimer la dépense.
HIGHEST_PRICE = max(PRICES_PER_MTOK.values(), key=lambda p: p[1])


def run_cost(model: str, input_tokens: int | None, output_tokens: int | None) -> float | None:
    """Coût en dollars ; `None` si le modèle est inconnu."""
    model = model.removeprefix("models/")  # Gemini préfixe parfois ses noms
    for prefix, (price_in, price_out) in PRICES_PER_MTOK.items():
        if model.startswith(prefix):
            return ((input_tokens or 0) * price_in + (output_tokens or 0) * price_out) / 1_000_000
    return None


def worst_case_cost(model: str, input_tokens: int | None, output_tokens: int | None) -> float:
    known = run_cost(model, input_tokens, output_tokens)
    if known is not None:
        return known
    price_in, price_out = HIGHEST_PRICE
    return ((input_tokens or 0) * price_in + (output_tokens or 0) * price_out) / 1_000_000
