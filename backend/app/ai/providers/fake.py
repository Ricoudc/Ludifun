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
from app.ai.schemas import (
    AnalysisOutput,
    EvaluationOutput,
    MaterialBatchOutput,
    OcrPage,
    OcrResult,
    SourcedAnswerOutput,
    SourceQuote,
)
from app.domain.activities.open_question import point_found

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
    data.setdefault("skills", [])
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
    defaults |= {"help": None, "open_questions": []}

    def v2(raw: dict[str, Any]) -> dict[str, Any]:
        """Distracteurs v1 (texte seul) → v2 ({text, misconception}), aides complétées."""
        questions = []
        for q in raw.get("questions", []):
            kinds = q.get("misconceptions", [])
            distractors = [
                d
                if isinstance(d, dict)
                else {"text": d, "misconception": kinds[i] if i < len(kinds) else None}
                for i, d in enumerate(q["distractors"])
            ]
            questions.append({**q, "distractors": distractors})
        help_ = raw.get("help")
        if help_ is not None:
            help_ = {"hint": None, "reminder": None, "example": None, "steps": [], **help_}
            if help_["example"] is not None:
                help_["example"] = {"why": None, **help_["example"]}
        return {**raw, "questions": questions, "help": help_}

    return MaterialBatchOutput.model_validate(
        {"materials": [{**defaults, **v2(material[k]), "knowledge_id": k} for k in ids if k in material]}
    )


_POINTS = re.compile(r"<points_cles>\n(.*?)\n</points_cles>", re.DOTALL)
_ANSWER = re.compile(r"<reponse_eleve>\n(.*?)\n</reponse_eleve>", re.DOTALL)


_SOURCE = re.compile(r'<source numero="(\d+)"[^>]*>\n(.*?)\n</source>', re.DOTALL)


def sources_output(input: str) -> SourcedAnswerOutput:
    """Réponse sourcée factice : la première phrase du premier extrait, citée mot pour mot."""
    match = _SOURCE.search(input)
    if match is None:
        return SourcedAnswerOutput(found=False, answer="", quotes=[])
    sentence = match.group(2).split(". ")[0].strip().rstrip(".") + "."
    return SourcedAnswerOutput(
        found=True,
        answer=f"D'après cette source : {sentence}",
        quotes=[SourceQuote(source=int(match.group(1)), text=sentence)],
    )


def evaluation_output(input: str) -> EvaluationOutput:
    """Correction factice, déterministe : les points clés dont les mots sont dans la réponse."""
    points_match, answer_match = _POINTS.search(input), _ANSWER.search(input)
    points = [p.removeprefix("- ") for p in points_match.group(1).splitlines()] if points_match else []
    answer = answer_match.group(1) if answer_match else ""
    found = [p for p in points if point_found(answer, p)]
    score = round(len(found) / len(points), 2) if points else 0.0
    return EvaluationOutput(
        score=score,
        key_points_found=found,
        missing=[p for p in points if p not in found],
        error_type=None if score == 1 else "forgotten" if not answer.strip() else "knowledge",
        confidence=0.9,
        feedback="Bravo, ta réponse est complète !"
        if score == 1
        else "C'est un début : relis la correction.",
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
        if stage == "evaluation":
            return evaluation_output(input)
        if stage == "sources":
            return sources_output(input)
        script = next((s for s in self.library if s.ocr_text.strip() in input), None)
        if stage == "analysis":
            if script is None:  # texte inconnu : comme un vrai modèle, « ce n'est pas une leçon »
                return analysis_output({"is_lesson": False, "lesson": None, "knowledge": [], "warnings": []})
            return analysis_output(script.analysis)
        return material_output((script or self.script).material, requested_ids(input))
