"""Pipeline « photos → leçon structurée → matériel pédagogique » (cahier des charges §5).

    ① OCR (reading) → ② analyse (analyzing) → ③ enrichissement (generating)

L'étape ④, l'assemblage des activités, n'utilise pas l'IA : elle est faite par le
composeur de séance au moment où l'élève commence à réviser.

Ce module ne touche pas à la base : l'appelant reçoit les changements d'étape
(`on_status`) et un `PipelineResult` complet, journal des appels IA compris.
"""

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel

from app.ai.ports import (
    AIError,
    AIInvalidOutput,
    LLMProvider,
    LLMResult,
    OcrProvider,
    PageImage,
    Prompt,
    Stage,
)
from app.ai.schemas import AnalysisOutput, MaterialBatchOutput, OcrPage, OcrResult
from app.domain.activities.registry import ActivityRegistry
from app.domain.knowledge import KnowledgeItem, KnowledgeUnit, LessonAnalysis
from app.domain.ocr_review import Uncertain, select_uncertain
from app.domain.understanding import required_levels
from app.domain.validation import (
    AnalysisError,
    MaterialValidation,
    Rejection,
    validate_analysis,
    validate_material,
)

logger = logging.getLogger("ludifun.lessons")
# Journal du serveur (Voir-les-erreurs-Ludifun.bat) : où en est l'IA, et combien de temps chaque étape.
STAGE_LABELS: dict[Stage, str] = {
    "ocr": "lecture de la leçon",
    "analysis": "identification des notions",
    "material": "préparation des exercices",
    "evaluation": "correction d'une réponse rédigée",
}
MATERIAL_BATCH = 5  # notions par appel d'enrichissement (appels en parallèle)
MIN_OPTIONS_IMPORTANT = 2  # activités minimales pour une notion d'importance ≥ 4 (§5.3)
IMPORTANT = 4
REJECTION_WARNING_RATE = 0.3  # au-delà, signal de qualité dans ai_runs (§6.4)


class LessonStatus(StrEnum):
    READING = "reading"
    ANALYZING = "analyzing"
    GENERATING = "generating"


class FailureReason(StrEnum):
    UNREADABLE = "unreadable"
    NOT_A_LESSON = "not_a_lesson"
    TOO_LONG = "too_long"
    AI_ERROR = "ai_error"


@dataclass
class AiRunRecord:
    """Une ligne de la table ai_runs : coût, latence et qualité d'un appel, sans contenu."""

    stage: Stage
    provider: str
    model: str
    prompt_version: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    status: str  # ok, invalid_output, refused, error
    warnings: list[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    failure_reason: FailureReason | None
    ocr: OcrResult | None = None
    analysis: LessonAnalysis | None = None
    units: list[KnowledgeUnit] = field(default_factory=list)
    required_levels: dict[str, frozenset[int]] = field(default_factory=dict)  # par notion retenue
    # Passages douteux à faire vérifier par l'enfant : l'analyse attend sa relecture.
    review: list[Uncertain] = field(default_factory=list)
    rejected: list[Rejection] = field(default_factory=list)
    runs: list[AiRunRecord] = field(default_factory=list)
    prompt_versions: dict[str, str] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.failure_reason is None and not self.review


class _Failed(Exception):
    def __init__(self, reason: FailureReason) -> None:
        self.reason = reason


StatusCallback = Callable[[LessonStatus], Awaitable[None]]


class LessonPipeline:
    def __init__(
        self,
        ocr: OcrProvider,
        llm: LLMProvider,
        registry: ActivityRegistry,
        *,
        max_chars: int = 20000,
        on_status: StatusCallback | None = None,
    ) -> None:
        self.ocr = ocr
        self.llm = llm
        self.registry = registry
        self.max_chars = max_chars
        self.on_status = on_status
        self.analysis_prompt = Prompt.load("analysis")
        self.material_prompt = Prompt.load("material")

    async def run(self, pages: Sequence[PageImage] = (), text: str | None = None) -> PipelineResult:
        """Analyse une leçon à partir de ses photos, ou directement de son texte (OCR déjà fait)."""
        result = PipelineResult(
            failure_reason=None,
            prompt_versions={
                "ocr": self.ocr.prompt_version,
                "analysis": self.analysis_prompt.version,
                "material": self.material_prompt.version,
            },
        )
        try:
            await self._run(result, tuple(pages), text)
        except _Failed as failure:
            result.failure_reason = failure.reason
        return result

    async def _run(self, result: PipelineResult, pages: tuple[PageImage, ...], text: str | None) -> None:
        # ① OCR
        await self._status(LessonStatus.READING)
        if text is None:
            try:
                ocr = await self._call(
                    result, "ocr", self.ocr.prompt_version, self.ocr.name, self.ocr.model,
                    lambda: self.ocr.extract(pages),
                )  # fmt: skip
            except AIError as exc:
                raise _Failed(FailureReason.AI_ERROR) from exc
            result.ocr = ocr.output
        else:
            result.ocr = OcrResult(
                pages=[OcrPage(index=0, quality="good", text=text)], language="fr", warnings=[]
            )
        if result.ocr.unreadable:
            raise _Failed(FailureReason.UNREADABLE)
        lesson_text = result.ocr.text
        if len(lesson_text) > self.max_chars:
            raise _Failed(FailureReason.TOO_LONG)
        if text is None:
            result.review = select_uncertain(
                (p.index, p.text, [(u.text, u.context) for u in p.uncertain]) for p in result.ocr.pages
            )
            if result.review:
                return  # « Peux-tu vérifier ? » : l'analyse reprendra sur le texte corrigé

        # ② Analyse pédagogique
        await self._status(LessonStatus.ANALYZING)
        analysis = await self._analyze(result, lesson_text)
        result.analysis = analysis
        if not analysis.is_lesson or not analysis.knowledge:
            raise _Failed(FailureReason.NOT_A_LESSON)

        # ③ Enrichissement
        await self._status(LessonStatus.GENERATING)
        result.units = await self._enrich(result, analysis, lesson_text)
        result.required_levels = {u.id: required_levels(u, self.registry) for u in result.units}
        if not result.units:
            raise _Failed(FailureReason.AI_ERROR)

    # ------------------------------------------------------------------ #

    async def _analyze(self, result: PipelineResult, text: str) -> LessonAnalysis:
        """Une relance si la sortie est inexploitable (hors schéma ou incohérente)."""
        for attempt in (1, 2):
            try:
                output = await self._call(
                    result,
                    "analysis",
                    self.analysis_prompt.version,
                    self.llm.name,
                    self.llm.model_for("analysis"),
                    lambda: self.llm.structured(
                        prompt=self.analysis_prompt, input=f"<lecon>\n{text}\n</lecon>", schema=AnalysisOutput
                    ),
                    retries=0,
                )
                validation = validate_analysis(output.output.to_raw(), text)
            except AIInvalidOutput as exc:
                if attempt == 2:
                    raise _Failed(FailureReason.AI_ERROR) from exc
                continue
            except AnalysisError as exc:
                result.runs[-1].status = "invalid_output"
                result.runs[-1].warnings.append(str(exc))
                if attempt == 2:
                    raise _Failed(FailureReason.AI_ERROR) from exc
                continue
            except AIError as exc:
                raise _Failed(FailureReason.AI_ERROR) from exc
            result.rejected += [Rejection(f"analysis.{r.element}", r.reason) for r in validation.rejected]
            result.runs[-1].warnings += [f"{r.element} : {r.reason}" for r in validation.rejected]
            return validation.analysis
        raise AssertionError("inaccessible")

    async def _enrich(
        self, result: PipelineResult, analysis: LessonAnalysis, text: str
    ) -> list[KnowledgeUnit]:
        items = analysis.knowledge
        batches = [items[i : i + MATERIAL_BATCH] for i in range(0, len(items), MATERIAL_BATCH)]
        validated: dict[str, MaterialValidation] = {}
        for found in await asyncio.gather(*(self._material(result, analysis, text, b) for b in batches)):
            validated |= found

        # Relance ciblée : notions importantes sans assez de matériel utilisable (§5.3).
        weak = [
            i
            for i in items
            if i.importance >= IMPORTANT and self._options(i, validated) < MIN_OPTIONS_IMPORTANT
        ]
        if weak:
            feedback = {i.id: validated[i.id].rejected for i in weak if i.id in validated}
            retried = await self._material(result, analysis, text, weak, feedback)
            for item in weak:
                if item.id in retried and self._options(item, retried) > self._options(item, validated):
                    validated[item.id] = retried[item.id]

        units, rejected = [], []
        for item in items:
            if item.id not in validated:
                rejected.append(Rejection(item.id, "aucun matériel produit"))
                continue
            validation = validated[item.id]
            rejected += [Rejection(f"{item.id}.{r.element}", r.reason) for r in validation.rejected]
            unit = KnowledgeUnit(item=item, material=validation.material)
            if self.registry.single_options(unit):
                units.append(unit)
            else:
                rejected.append(Rejection(item.id, "aucune activité possible avec le matériel validé"))
        result.rejected += rejected

        material_runs = [r for r in result.runs if r.stage == "material"]
        dropped = sum(len(v.rejected) for v in validated.values())
        total = dropped + sum(v.kept for v in validated.values())
        rate = dropped / total if total else 0.0
        if material_runs and rate > REJECTION_WARNING_RATE:
            material_runs[-1].warnings.append(f"taux de rejet du matériel élevé : {rate:.0%}")
        return units

    async def _material(
        self,
        result: PipelineResult,
        analysis: LessonAnalysis,
        text: str,
        items: list[KnowledgeItem],
        feedback: dict[str, list[Rejection]] | None = None,
    ) -> dict[str, MaterialValidation]:
        try:
            output = await self._call(
                result,
                "material",
                self.material_prompt.version,
                self.llm.name,
                self.llm.model_for("material"),
                lambda: self.llm.structured(
                    prompt=self.material_prompt,
                    input=_material_input(analysis, text, items, feedback),
                    schema=MaterialBatchOutput,
                ),
            )
        except AIError:
            return {}  # les notions de ce lot n'auront pas de matériel ; la relance ciblée peut les rattraper
        by_id = {i.id: i for i in items}
        found: dict[str, MaterialValidation] = {}
        for material in output.output.materials:
            if material.knowledge_id in by_id and material.knowledge_id not in found:
                found[material.knowledge_id] = validate_material(
                    by_id[material.knowledge_id], material.model_dump(mode="json")
                )
        result.runs[-1].warnings += [
            f"{k}.{r.element} : {r.reason}" for k, v in found.items() for r in v.rejected
        ]
        return found

    def _options(self, item: KnowledgeItem, validated: dict[str, MaterialValidation]) -> int:
        if item.id not in validated:
            return 0
        return len(
            self.registry.single_options(KnowledgeUnit(item=item, material=validated[item.id].material))
        )

    async def _call[T: BaseModel](
        self,
        result: PipelineResult,
        stage: Stage,
        prompt_version: str,
        provider: str,
        model: str,
        call: Callable[[], Awaitable[LLMResult[T]]],
        retries: int = 1,
    ) -> LLMResult[T]:
        """Appel journalisé dans ai_runs ; relance si la sortie est hors schéma.

        Les erreurs réseau et de quota sont déjà relancées par le SDK du fournisseur.
        """
        for attempt in range(retries + 1):
            started = time.perf_counter()
            logger.info("IA : %s en cours (%s)…", STAGE_LABELS[stage], model)
            try:
                response = await call()
            except AIError as exc:
                latency = round((time.perf_counter() - started) * 1000)
                logger.warning("IA : %s en échec après %d s : %s", STAGE_LABELS[stage], latency // 1000, exc)
                result.runs.append(
                    AiRunRecord(
                        stage, provider, model, prompt_version, None, None, latency, exc.status, [str(exc)]
                    )
                )
                if isinstance(exc, AIInvalidOutput) and attempt < retries:
                    continue
                raise
            usage = response.usage
            logger.info("IA : %s terminée en %d s", STAGE_LABELS[stage], (usage.latency_ms or 0) // 1000)
            result.runs.append(
                AiRunRecord(
                    stage,
                    usage.provider,
                    usage.model,
                    prompt_version,
                    usage.input_tokens,
                    usage.output_tokens,
                    usage.latency_ms,
                    "ok",
                )
            )
            return response
        raise AssertionError("inaccessible")

    async def _status(self, status: LessonStatus) -> None:
        if self.on_status is not None:
            await self.on_status(status)


def _material_input(
    analysis: LessonAnalysis,
    text: str,
    items: list[KnowledgeItem],
    feedback: dict[str, list[Rejection]] | None,
) -> str:
    lesson = analysis.lesson
    assert lesson is not None
    notions = [
        {
            "id": i.id,
            "type": i.type,
            "label": i.label,
            "statement": i.statement,
            "importance": i.importance,
            "attributes": i.attributes,
        }
        for i in items
    ]
    parts = [
        f"Matière : {lesson.subject} · niveau : {lesson.grade} · leçon : {lesson.title}",
        f"<lecon>\n{text}\n</lecon>",
        f"<notions>\n{json.dumps({'notions': notions}, ensure_ascii=False, indent=1)}\n</notions>",
    ]
    if feedback and any(feedback.values()):
        refused = [f"- {k} · {r.element} : {r.reason}" for k, rs in feedback.items() for r in rs]
        parts.append(
            "Une première version a été refusée pour ces raisons ; corrige-les :\n" + "\n".join(refused)
        )
    parts.append("Produis le matériel de révision de chacune de ces notions.")
    return "\n\n".join(parts)
