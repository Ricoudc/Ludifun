"""Évaluation du pipeline sur un corpus de vraies leçons (cahier des charges §17.2).

    uv run python -m app.tools.evaluate ../eval/lessons
    uv run python -m app.tools.evaluate ../eval/example --provider fake

Chaque leçon est un dossier contenant ses photos (page1.jpg, page2.jpg…) ou un
`lesson.txt`, et un `expected.json` annoté par un adulte (voir eval/README.md).
Le résultat est écrit dans un dossier horodaté : un rapport `report.md`, et pour
chaque leçon le résultat complet (`<leçon>.json`) et la séance à relire (`<leçon>.txt`).
"""

import argparse
import asyncio
import io
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.ai.factory import build_providers
from app.ai.ports import PageImage
from app.config import get_settings
from app.domain.activities.registry import default_registry
from app.domain.knowledge import Grade, KnowledgeItem, Subject
from app.domain.text import contains_words, normalize
from app.services.lesson_pipeline import LessonPipeline, PipelineResult
from app.tools.analyze import media_type, report, to_json

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
GRADES = [g.value for g in Grade]

# Prix publics en dollars par million de jetons (entrée, sortie). Les jetons de
# réflexion sont comptés en sortie ; les lectures de cache, moins chères, sont
# comptées au plein tarif : l'estimation est donc prudente.
PRICES_PER_MTOK = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-fable-5": (10.0, 50.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "fake": (0.0, 0.0),
}


class ExpectedNotion(BaseModel):
    label: str
    aliases: list[str] = Field(default_factory=list)


class Expected(BaseModel):
    """Annotation d'une leçon par un adulte (`expected.json`)."""

    subject: Subject
    grade: Grade
    support: str = "inconnu"  # manuscrit, manuel, photocopie…
    essential: list[ExpectedNotion]  # notions indispensables pour une interrogation
    is_lesson: bool = True  # false pour un cas piège (photo qui n'est pas une leçon)
    notes: str = ""


@dataclass
class LessonScore:
    name: str
    pages: int
    support: str
    expected: Expected
    failure: str | None
    duration_s: float
    subject_ok: bool | None = None
    grade_ok: bool | None = None
    found: dict[str, str | None] = field(default_factory=dict)  # notion attendue → notion produite
    invented: int = 0  # notions rejetées car introuvables dans le texte
    material_kept: int = 0
    material_rejected: int = 0
    cost_usd: float | None = 0.0
    tokens: tuple[int, int] = (0, 0)

    @property
    def recall(self) -> float | None:
        return sum(v is not None for v in self.found.values()) / len(self.found) if self.found else None

    @property
    def correct_outcome(self) -> bool:
        """Une leçon doit aboutir ; un cas piège doit être refusé."""
        if self.expected.is_lesson:
            return self.failure is None
        return self.failure in ("not_a_lesson", "unreadable")


def match_notion(expected: ExpectedNotion, knowledge: list[KnowledgeItem]) -> str | None:
    """Notion produite qui correspond à une notion attendue (libellé ou variante)."""
    names = [expected.label, *expected.aliases]
    for item in knowledge:
        text = f"{item.label} {item.statement}"
        for name in names:
            if (
                contains_words(text, name)
                or SequenceMatcher(None, normalize(item.label), normalize(name)).ratio() >= 0.85
            ):
                return item.id
    return None


def run_cost(model: str, input_tokens: int | None, output_tokens: int | None) -> float | None:
    for prefix, (price_in, price_out) in PRICES_PER_MTOK.items():
        if model.startswith(prefix):
            return ((input_tokens or 0) * price_in + (output_tokens or 0) * price_out) / 1_000_000
    return None


def material_counts(result: PipelineResult) -> tuple[int, int]:
    kept = 0
    for unit in result.units:
        m = unit.material
        kept += len(m.questions) + len(m.true_statements) + len(m.false_statements)
        kept += sum(x is not None for x in (m.cloze, m.pair, m.flashcard, m.tip))
    rejected = sum(1 for r in result.rejected if "." in r.element and not r.element.startswith("analysis."))
    return kept, rejected


def score(
    name: str, expected: Expected, result: PipelineResult, pages: int, duration_s: float
) -> LessonScore:
    s = LessonScore(name, pages, expected.support, expected, result.failure_reason, duration_s)
    costs = [run_cost(r.model, r.input_tokens, r.output_tokens) for r in result.runs]
    s.cost_usd = None if None in costs else sum(c or 0.0 for c in costs)
    s.tokens = (sum(r.input_tokens or 0 for r in result.runs), sum(r.output_tokens or 0 for r in result.runs))
    s.invented = sum(
        1 for r in result.rejected if r.element.startswith("analysis.") and "introuvable" in r.reason
    )
    s.material_kept, s.material_rejected = material_counts(result)
    analysis = result.analysis
    if expected.is_lesson and analysis is not None and analysis.lesson is not None:
        lesson = analysis.lesson
        s.subject_ok = lesson.subject == expected.subject
        s.grade_ok = abs(GRADES.index(lesson.grade) - GRADES.index(expected.grade)) <= 1
    if expected.is_lesson:
        knowledge = analysis.knowledge if analysis else []
        s.found = {n.label: match_notion(n, knowledge) for n in expected.essential}
    return s


# --------------------------------------------------------------------------- #
# Rapport
# --------------------------------------------------------------------------- #


def _pct(values: list[bool]) -> float | None:
    return 100 * sum(values) / len(values) if values else None


def _fmt(value: float | None, suffix: str = " %") -> str:
    return "—" if value is None else f"{value:.0f}{suffix}"


@dataclass
class Metric:
    name: str
    value: float | None
    display: str
    target: str
    ok: bool | None


def metrics(scores: list[LessonScore]) -> list[Metric]:
    lessons = [s for s in scores if s.expected.is_lesson]
    analysed = [s for s in scores if s.subject_ok is not None]
    success = _pct([s.correct_outcome for s in scores])
    subject = _pct([bool(s.subject_ok) for s in analysed])
    grade = _pct([bool(s.grade_ok) for s in analysed])
    found = [v is not None for s in lessons for v in s.found.values()]
    recall = _pct(found)
    invented = sum(s.invented for s in scores)
    kept = sum(s.material_kept for s in scores)
    rejected = sum(s.material_rejected for s in scores)
    rejection = 100 * rejected / (kept + rejected) if kept + rejected else None
    two_pages = [s.duration_s for s in scores if s.pages == 2 and s.failure is None]
    any_pages = [s.duration_s for s in scores if s.failure is None]
    durations = two_pages or any_pages
    median = statistics.median(durations) if durations else None
    costs = [s.cost_usd for s in scores if s.cost_usd is not None and s.failure is None]
    mean_cost = statistics.mean(costs) if costs else None

    def at_least(value: float | None, target: float) -> bool | None:
        return None if value is None else value >= target

    return [
        Metric("Leçons traitées correctement", success, _fmt(success), "≥ 90 %", at_least(success, 90)),
        Metric("Matière correcte", subject, _fmt(subject), "≥ 95 %", at_least(subject, 95)),
        Metric("Niveau à ± 1 classe", grade, _fmt(grade), "≥ 80 %", at_least(grade, 80)),
        Metric("Rappel des notions indispensables", recall, _fmt(recall), "≥ 85 %", at_least(recall, 85)),
        Metric("Notions inventées (rejetées)", invented, str(invented), "0", invented == 0),
        Metric(
            "Matériel rejeté par les validateurs",
            rejection,
            _fmt(rejection),
            "≤ 15 %",
            None if rejection is None else rejection <= 15,
        ),
        Metric(
            "Durée photo → prête (médiane" + (", 2 pages)" if two_pages else ")"),
            median,
            _fmt(median, " s"),
            "≤ 45 s",
            None if median is None else median <= 45,
        ),
        Metric(
            "Coût IA moyen par leçon",
            mean_cost,
            "—" if mean_cost is None else f"{mean_cost:.3f} $",
            "à fixer",
            None,
        ),
    ]


def render_report(scores: list[LessonScore], provider: str, started: datetime) -> str:
    icon = {True: "✅", False: "❌", None: "·"}
    lines = [
        f"# Évaluation du pipeline — {started:%Y-%m-%d %H:%M} UTC",
        "",
        f"Fournisseur : `{provider}` · {len(scores)} leçon(s)",
        "",
        "## Mesures (§17.2)",
        "",
        "| Mesure | Valeur | Seuil V1 | |",
        "|---|---|---|---|",
    ]
    lines += [f"| {m.name} | {m.display} | {m.target} | {icon[m.ok]} |" for m in metrics(scores)]
    lines += [
        "",
        "## Par leçon",
        "",
        "| Leçon | Support | Pages | Issue | Matière | Niveau | Rappel | Inventées "
        "| Rejets matériel | Durée | Coût |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in scores:
        outcome = "prête" if s.failure is None else s.failure
        if not s.expected.is_lesson:
            outcome += " (piège)"
        total = s.material_kept + s.material_rejected
        rejects = f"{s.material_rejected}/{total}" if total else "—"
        cost = "—" if s.cost_usd is None else f"{s.cost_usd:.3f} $"
        recall = _fmt(None if s.recall is None else 100 * s.recall)
        lines.append(
            f"| {s.name} | {s.support} | {s.pages} | {icon[s.correct_outcome]} {outcome} "
            f"| {icon[s.subject_ok]} | {icon[s.grade_ok]} | {recall} "
            f"| {s.invented} | {rejects} | {s.duration_s:.1f} s | {cost} |"
        )
    missed = [(s.name, label) for s in scores for label, found in s.found.items() if found is None]
    if missed:
        lines += ["", "## Notions indispensables manquées", ""]
        lines += [f"- **{name}** : {label}" for name, label in missed]
    lines += [
        "",
        "## À faire ensuite",
        "",
        "- Relire les séances (`<leçon>.txt`) avec la grille `eval/grille-evaluation.md`.",
        "- Pour chaque ❌, ouvrir `<leçon>.json` : texte lu, notions, éléments rejetés et raisons.",
    ]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Exécution
# --------------------------------------------------------------------------- #


@dataclass
class LessonInput:
    name: str
    expected: Expected
    pages: list[PageImage]
    text: str | None


def load_corpus(root: Path, only: set[str] | None = None) -> list[LessonInput]:
    lessons = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        if only and folder.name not in only:
            continue
        expected_file = folder / "expected.json"
        if not expected_file.exists():
            print(f"⚠ {folder.name} ignorée : pas de expected.json", file=sys.stderr)
            continue
        expected = Expected.model_validate_json(expected_file.read_text(encoding="utf-8"))
        text_file = folder / "lesson.txt"
        text = text_file.read_text(encoding="utf-8") if text_file.exists() else None
        images = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
        pages = [PageImage(p.read_bytes(), media_type(p.read_bytes(), p)) for p in images]
        if text is None and not pages:
            print(f"⚠ {folder.name} ignorée : ni photo ni lesson.txt", file=sys.stderr)
            continue
        lessons.append(LessonInput(folder.name, expected, pages, text))
    return lessons


async def evaluate(
    lessons: list[LessonInput], provider: str | None, concurrency: int
) -> list[tuple[LessonInput, PipelineResult, float]]:
    settings = get_settings()
    if provider:
        settings = settings.model_copy(update={"ai_provider": provider})
    ocr, llm = build_providers(settings)
    pipeline = LessonPipeline(ocr, llm, default_registry(), max_chars=settings.max_lesson_chars)
    semaphore = asyncio.Semaphore(concurrency)

    async def one(lesson: LessonInput) -> tuple[LessonInput, PipelineResult, float]:
        async with semaphore:
            started = time.perf_counter()
            result = await pipeline.run(lesson.pages, lesson.text)
            duration = time.perf_counter() - started
            print(
                f"  {lesson.name} : {result.failure_reason or 'prête'} en {duration:.1f} s", file=sys.stderr
            )
            return lesson, result, duration

    return list(await asyncio.gather(*(one(lesson) for lesson in lessons)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.tools.evaluate", description=__doc__.split("\n")[0])
    parser.add_argument("corpus", type=Path, help="dossier contenant un sous-dossier par leçon")
    parser.add_argument("--out", type=Path, help="dossier des résultats (défaut : <corpus>/../results)")
    parser.add_argument(
        "--provider", choices=["claude", "fake"], help="fournisseur d'IA (défaut : configuration)"
    )
    parser.add_argument("--only", help="noms de leçons séparés par des virgules")
    parser.add_argument("--concurrency", type=int, default=3, help="leçons traitées en parallèle")
    args = parser.parse_args(argv)

    lessons = load_corpus(args.corpus, set(args.only.split(",")) if args.only else None)
    if not lessons:
        parser.error(f"aucune leçon exploitable dans {args.corpus}")

    started = datetime.now(UTC)
    provider = args.provider or get_settings().ai_provider
    print(f"Évaluation de {len(lessons)} leçon(s) avec « {provider} »…", file=sys.stderr)
    runs = asyncio.run(evaluate(lessons, args.provider, args.concurrency))

    out = (args.out or args.corpus.resolve().parent / "results") / f"{started:%Y%m%d-%H%M%S}"
    out.mkdir(parents=True, exist_ok=True)
    scores = []
    for lesson, result, duration in runs:
        s = score(lesson.name, lesson.expected, result, len(lesson.pages) or 1, duration)
        scores.append(s)
        details: dict[str, Any] = to_json(result) | {
            "duration_s": round(duration, 2),
            "cost_usd": s.cost_usd,
            "essential_found": s.found,
        }
        (out / f"{lesson.name}.json").write_text(
            json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        session = io.StringIO()
        report(result, seed=1, out=session)
        (out / f"{lesson.name}.txt").write_text(session.getvalue(), encoding="utf-8")

    text = render_report(scores, provider, started)
    (out / "report.md").write_text(text, encoding="utf-8")
    print(text)
    print(f"Résultats détaillés : {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
