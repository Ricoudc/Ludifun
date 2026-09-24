"""Interfaces des fournisseurs d'IA (cahier des charges §5.4).

Le pipeline ne connaît que ces interfaces : changer de modèle, de fournisseur d'IA
ou de service d'OCR revient à écrire un nouvel adaptateur.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel

Stage = Literal["ocr", "analysis", "material", "evaluation"]
MediaType = Literal["image/jpeg", "image/png", "image/webp", "image/gif"]
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
PROMPT_VERSIONS: dict[Stage, str] = {"ocr": "v1", "analysis": "v2", "material": "v2", "evaluation": "v1"}


@dataclass(frozen=True)
class PageImage:
    data: bytes
    media_type: MediaType


@dataclass(frozen=True)
class Prompt:
    stage: Stage
    version: str
    text: str

    @classmethod
    def load(cls, stage: Stage, version: str | None = None) -> "Prompt":
        version = version or PROMPT_VERSIONS[stage]
        return cls(stage, version, (PROMPTS_DIR / f"{stage}.{version}.md").read_text(encoding="utf-8"))

    @property
    def id(self) -> str:
        return f"{self.stage}.{self.version}"


@dataclass(frozen=True)
class Usage:
    provider: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int


@dataclass(frozen=True)
class LLMResult[T: BaseModel]:
    output: T
    usage: Usage


class AIError(Exception):
    """Erreur d'appel au fournisseur (réseau, quota, service indisponible…)."""

    status = "error"


class AIRefused(AIError):
    """Le modèle a refusé de traiter la demande."""

    status = "refused"


class AIInvalidOutput(AIError):
    """La réponse ne respecte pas le schéma attendu (ou est tronquée)."""

    status = "invalid_output"


class LLMProvider(Protocol):
    name: str

    def model_for(self, stage: Stage) -> str: ...

    async def structured[T: BaseModel](
        self, *, prompt: Prompt, input: str, schema: type[T], images: tuple[PageImage, ...] = ()
    ) -> LLMResult[T]: ...


class OcrProvider(Protocol):
    """① Lecture des photos : texte par page et qualité de lecture."""

    name: str
    model: str
    prompt_version: str

    async def extract(self, pages: tuple[PageImage, ...]) -> "LLMResult[OcrResult]": ...


from app.ai.schemas import OcrResult  # noqa: E402  (évite une importation circulaire)
