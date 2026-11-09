"""Adresses d'IA libres des familles (§5.70) : jamais ce qui est derrière le serveur (SSRF)."""

import pytest

from app.ai.url_safety import refused_ai_url

OLLAMA = frozenset({"host.docker.internal"})


@pytest.mark.parametrize(
    "url",
    [
        "http://db:5432",  # la base de Ludifun
        "http://recherche:8080/search",  # le moteur de recherche interne
        "http://169.254.169.254/latest/meta-data/",  # métadonnées de l'hébergeur
        "http://[fe80::1]:11434",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://0.0.0.0:11434",
        "http://parent:secret@ollama.maison:11434",  # identifiants dans l'adresse
        "ftp://exemple.fr/v1",
        "http://",
    ],
)
def test_always_refused(url: str) -> None:
    assert refused_ai_url(url, strict=False, allowed=OLLAMA) is not None
    assert refused_ai_url(url, strict=True, allowed=OLLAMA) is not None


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:11434",  # Ollama sur le PC
        "http://127.0.0.1:11434",
        "http://192.168.1.20:11434",  # Ollama sur un autre ordinateur de la maison
        "http://10.0.0.5:11434/v1",
        "http://[::1]:11434",
    ],
)
def test_the_family_pc_may_use_its_own_network(url: str) -> None:
    assert refused_ai_url(url, strict=False, allowed=OLLAMA) is None
    # Serveur partagé (production) : ni la machine ni le réseau local.
    assert "réseau local" in (refused_ai_url(url, strict=True, allowed=OLLAMA) or "")


def test_public_services_and_the_servers_own_ollama() -> None:
    for strict in (False, True):
        assert refused_ai_url("https://openrouter.ai/api/v1", strict=strict) is None
        assert refused_ai_url("https://x.openai.azure.com/openai/v1", strict=strict) is None
        assert refused_ai_url("http://host.docker.internal:11434", strict=strict, allowed=OLLAMA) is None
