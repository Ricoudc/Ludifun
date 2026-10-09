"""Interface d'un moteur d'images."""

from dataclasses import dataclass
from typing import Protocol


class ImageEngineError(Exception):
    """Le moteur n'a pas produit d'image (absent, en panne, délai dépassé)."""


@dataclass(frozen=True)
class ImageRequest:
    prompt: str
    negative_prompt: str
    width: int
    height: int
    seed: int
    # SDXL-Lightning 4 étapes : Euler, sgm_uniform, sans guidage (CFG 1), comme le recommande
    # ByteDance. Un autre modèle se règle ici, sans toucher au reste.
    steps: int = 4
    cfg_scale: float = 1.0
    sampler: str = "euler"
    scheduler: str = "sgm_uniform"


@dataclass(frozen=True)
class GeneratedImage:
    data: bytes  # PNG ou JPEG, vérifié par les premiers octets
    media_type: str
    engine: str
    model: str
    latency_ms: int


class ImageEngine(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    @property
    def base_url(self) -> str | None:
        """Adresse du moteur sur le PC (None : moteur en mémoire ou en ligne, rien à décharger)."""

    async def generate(self, request: ImageRequest) -> GeneratedImage: ...

    async def release(self) -> None:
        """Libère la carte graphique (modèle déchargé) ; sans effet si le moteur le fait seul."""
