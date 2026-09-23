"""Fournisseur d'IA factice et déterministe, pour les tests et le développement sans clé.

Il rejoue une leçon de référence (`reference_lessons/*.json`) : texte OCR, analyse et
matériel. Les tests peuvent remplacer une réponse par étape (`overrides`) pour
simuler une erreur, un refus ou une sortie de mauvaise qualité.
"""

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.ai.ports import LLMResult, PageImage, Prompt, Stage, Usage
from app.ai.schemas import AnalysisOutput, MaterialBatchOutput, OcrPage, OcrResult

REFERENCE_LESSONS = Path(__file__).resolve().parents[3] / "reference_lessons"
DEMO_LESSON = REFERENCE_LESSONS / "history_cm1_revolution.json"
_NOTIONS = re.compile(r"<notions>(.*?)</notions>", re.DOTALL)


@dataclass(frozen=True)
class LessonScript:
    ocr_text: str
    analysis: dict[str, Any]
    material: dict[str, dict[str, Any]]

    @classmethod
    def from_file(cls, path: Path) -> "LessonScript":
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(raw["ocr_text"], raw["analysis"], raw["material"])


# Une réponse de remplacement : une sortie, une exception à lever, ou une fonction
# (numéro d'appel de l'étape, texte envoyé) → sortie ou exception.
Override = BaseModel | Exception | Callable[[int, str], BaseModel | Exception]


def requested_ids(input: str) -> list[str]:
    """Identifiants des notions demandées dans une requête d'enrichissement."""
    match = _NOTIONS.search(input)
    if not match:
        return []
    return [n["id"] for n in json.loads(match.group(1))["notions"]]


def analysis_output(raw: dict[str, Any]) -> AnalysisOutput:
    data = json.loads(json.dumps(raw))
    for item in data.get("knowledge", []):
        attributes = item.get("attributes", {})
        if isinstance(attributes.get("variables"), dict):
            attributes["variables"] = [
                {"symbol": k, "meaning": v} for k, v in attributes["variables"].items()
            ]
    return AnalysisOutput.model_validate(data)


def material_output(material: dict[str, dict[str, Any]], ids: list[str]) -> MaterialBatchOutput:
    defaults: dict[str, Any] = {"questions": [], "true_statements": [], "false_statements": []}
    defaults |= {"cloze": None, "pair": None, "flashcard": None, "tip": None}
    return MaterialBatchOutput.model_validate(
        {"materials": [{**defaults, **material[k], "knowledge_id": k} for k in ids if k in material]}
    )


class FakeProvider:
    name = "fake"

    def __init__(
        self, script: LessonScript | None = None, overrides: dict[Stage, Override] | None = None
    ) -> None:
        self.script = script or LessonScript.from_file(DEMO_LESSON)
        # Sans leçon imposée, l'analyse d'un texte rejoue la leçon de référence correspondante.
        self.library = (
            [self.script]
            if script
            else [LessonScript.from_file(path) for path in sorted(REFERENCE_LESSONS.glob("*.json"))]
        )
        self.overrides = overrides or {}
        self.calls: list[tuple[Stage, str]] = []

    def model_for(self, stage: Stage) -> str:
        return "fake"

    async def structured[T: BaseModel](
        self, *, prompt: Prompt, input: str, schema: type[T], images: tuple[PageImage, ...] = ()
    ) -> LLMResult[T]:
        started = time.perf_counter()
        self.calls.append((prompt.stage, input))
        attempt = sum(1 for stage, _ in self.calls if stage == prompt.stage)

        output: BaseModel | Exception
        override = self.overrides.get(prompt.stage)
        if override is None:
            output = self._scripted(prompt.stage, input, len(images))
        elif isinstance(override, BaseModel | Exception):
            output = override
        else:
            output = override(attempt, input)
        if isinstance(output, Exception):
            raise output
        if not isinstance(output, schema):
            raise TypeError(f"réponse factice {type(output).__name__} au lieu de {schema.__name__}")
        latency = round((time.perf_counter() - started) * 1000)
        return LLMResult(output, Usage(self.name, "fake", 0, 0, latency))

    def _scripted(self, stage: Stage, input: str, images: int) -> BaseModel:
        if stage == "ocr":
            pages = [
                OcrPage(index=i, quality="good", text=self.script.ocr_text if i == 0 else "")
                for i in range(images)
            ]
            return OcrResult(pages=pages, language="fr", warnings=[])
        script = next((s for s in self.library if s.ocr_text.strip() in input), None)
        if stage == "analysis":
            if script is None:  # texte inconnu : comme un vrai modèle, « ce n'est pas une leçon »
                return analysis_output({"is_lesson": False, "lesson": None, "knowledge": [], "warnings": []})
            return analysis_output(script.analysis)
        return material_output((script or self.script).material, requested_ids(input))
