"""Analyse une leçon depuis le terminal, sans application ni base (étapes 4 et 5).

    uv run python -m app.tools.analyze photo1.jpg photo2.jpg
    uv run python -m app.tools.analyze --text lecon.txt
    uv run python -m app.tools.analyze photo.jpg --provider fake --json resultat.json

Affiche la leçon comprise, les notions (avec les niveaux de compréhension exigés : 1 reconnaître,
2 se rappeler, 3 appliquer), les compétences, les éléments rejetés par les validateurs,
une première séance composée, et le coût des appels IA.
"""

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from app.ai.factory import build_providers
from app.ai.images import detect_media_type
from app.ai.ports import MediaType, PageImage
from app.ai.presets import PRESETS
from app.config import get_settings
from app.domain.activities.base import ActivityCode, BuiltActivity
from app.domain.activities.registry import default_registry
from app.domain.composer import Block, SessionComposer
from app.services.lesson_pipeline import LessonPipeline, LessonStatus, PipelineResult

BLOCK_TITLES = {
    Block.WARMUP: "🧠 Échauffement",
    Block.CORE: "🎯 Approfondissement",
    Block.MATCH: "🧩 Association",
    Block.SPEED: "⚡ Défi rapide",
    Block.REPLAY: "🔄 Reprise",
}
FAILURES = {
    "unreadable": "Je n'arrive pas à lire ta photo. Reprends-la avec plus de lumière.",
    "not_a_lesson": "Ça ne ressemble pas à une leçon.",
    "too_long": "La leçon est trop longue.",
    "ai_error": "Petit souci du côté de l'IA, réessaie.",
}


def media_type(data: bytes, path: Path) -> MediaType:
    detected = detect_media_type(data)
    if detected is None:
        raise SystemExit(f"{path} : format non pris en charge (JPEG, PNG, WebP ou GIF ; convertir les HEIC)")
    return detected


def render_activity(activity: BuiltActivity) -> list[str]:
    p, s = activity.payload, activity.solution
    match activity.type:
        case ActivityCode.MCQ:
            lines = [f"QCM · {p['prompt']}"]
            lines += [f"    {'✓' if c['id'] == s['choice_id'] else ' '} {c['text']}" for c in p["choices"]]
            return lines
        case ActivityCode.TRUE_FALSE:
            return [f"Vrai ou faux · {p['statement']}", f"    → {s['display']}"]
        case ActivityCode.FILL_BLANK:
            return [f"Texte à trous · {p['text']}", f"    → {' / '.join(s['answers'])}"]
        case ActivityCode.FLASHCARD:
            return [f"Carte mémoire · {p['front']}", f"    → {p['back']}"]
        case ActivityCode.MATCH:
            return ["Association"] + [f"    {line}" for line in s["display"].split(" ; ")]
        case ActivityCode.SPEED_CHALLENGE:
            lines = [f"Défi rapide ({p['time_limit_s']} s)"]
            lines += [f"    {'V' if s['answers'][x['id']] else 'F'} {x['text']}" for x in p["statements"]]
            return lines
    return [str(activity.type)]


def report(result: PipelineResult, seed: int, out: TextIO) -> None:
    def say(line: str = "") -> None:
        print(line, file=out)

    if result.ocr is not None:
        say("══ Texte lu ══")
        say(result.ocr.text)
        for warning in result.ocr.warnings:
            say(f"⚠ {warning}")
        say()

    analysis = result.analysis
    if analysis is not None and analysis.lesson is not None:
        lesson = analysis.lesson
        say("══ Leçon ══")
        say(f"{lesson.subject.upper()} · {lesson.grade} (confiance {lesson.grade_confidence:.0%})")
        say(lesson.title.upper())
        say(f"🎯 {lesson.objective}")
        say(lesson.summary)
        say()
        say("══ Notions ══")
        kept = {u.id for u in result.units}
        for notion in analysis.knowledge:
            mark = "✓" if notion.id in kept else "✗"
            stars = "★" * notion.importance
            levels = ", ".join(str(level) for level in sorted(result.required_levels.get(notion.id, ())))
            niveaux = f", niveaux {levels}" if levels else ""
            say(f"{mark} {notion.id} [{notion.type}, {stars}{niveaux}] {notion.label} — {notion.statement}")
        say()
        say("══ Compétences ══")
        for skill in analysis.skills:
            notions = ", ".join(skill.knowledge_ids)
            say(f"  {skill.id} [{skill.verb}, {'★' * skill.importance}] {skill.label} ({notions})")
        say()

    if result.rejected:
        say(f"══ Rejeté par les validateurs ({len(result.rejected)}) ══")
        for r in result.rejected:
            say(f"  {r.element} : {r.reason}")
        say()

    if result.ready:
        registry = default_registry()
        plan = SessionComposer(registry).compose(result.units, {}, now=datetime.now(UTC), seed=seed)
        say(f"══ Séance (graine {seed}) · durée estimée {plan.estimated_minutes} min ══")
        current: Block | None = None
        for item in plan.items:
            if item.block != current:
                current = item.block
                say(BLOCK_TITLES[item.block])
            lines = render_activity(item.activity)
            say(f"  {item.position}. {lines[0]}  ({', '.join(item.activity.knowledge_ids)})")
            for line in lines[1:]:
                say(f"  {line}")
        say()
    else:
        assert result.failure_reason is not None
        say(f"✗ Échec : {result.failure_reason} — {FAILURES[result.failure_reason]}")
        say()

    say("══ Appels IA ══")
    tokens_in = tokens_out = latency = 0
    for run in result.runs:
        tokens_in += run.input_tokens or 0
        tokens_out += run.output_tokens or 0
        latency += run.latency_ms
        say(
            f"  {run.stage:<9} {run.status:<15} {run.model:<18} {run.prompt_version} "
            f"in={run.input_tokens} out={run.output_tokens} {run.latency_ms} ms"
        )
        for warning in run.warnings[:5]:
            say(f"      ⚠ {warning}")
    say(f"  Total : {tokens_in} jetons en entrée, {tokens_out} en sortie, {latency / 1000:.1f} s cumulées")


def to_json(result: PipelineResult) -> dict[str, Any]:
    return {
        "failure_reason": result.failure_reason,
        "ocr_text": result.ocr.text if result.ocr else None,
        "analysis": result.analysis.model_dump(mode="json") if result.analysis else None,
        "material": {u.id: u.material.model_dump(mode="json") for u in result.units},
        "rejected": [asdict(r) for r in result.rejected],
        "runs": [asdict(r) for r in result.runs],
        "prompt_versions": result.prompt_versions,
    }


async def analyze(pages: list[PageImage], text: str | None, provider: str | None) -> PipelineResult:
    settings = get_settings()
    if provider:
        settings = settings.model_copy(update={"ai_provider": provider})
    ocr, llm = build_providers(settings)

    async def on_status(status: LessonStatus) -> None:
        labels = {
            LessonStatus.READING: "🔎 Lecture de ta leçon…",
            LessonStatus.ANALYZING: "🧠 Identification des notions…",
            LessonStatus.GENERATING: "🎮 Préparation de tes exercices…",
        }
        print(labels[status], file=sys.stderr)

    pipeline = LessonPipeline(
        ocr, llm, default_registry(), max_chars=settings.max_lesson_chars, on_status=on_status
    )
    return await pipeline.run(pages, text)


def main(argv: list[str] | None = None, out: TextIO = sys.stdout) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.tools.analyze", description=__doc__.split("\n")[0])
    parser.add_argument("photos", nargs="*", help="photos de la leçon, dans l'ordre des pages (6 au plus)")
    parser.add_argument("--text", help="fichier texte de la leçon (saute l'OCR)")
    parser.add_argument(
        "--provider", choices=[*sorted(PRESETS), "fake"], help="fournisseur d'IA (défaut : configuration)"
    )
    parser.add_argument("--seed", type=int, default=1, help="graine de la séance composée")
    parser.add_argument("--json", help="enregistre le résultat complet dans ce fichier")
    args = parser.parse_args(argv)
    if not args.text and not args.photos:
        parser.error("donner au moins une photo ou --text")
    if len(args.photos) > 6:
        parser.error("6 pages au plus")

    text = Path(args.text).read_text(encoding="utf-8") if args.text else None
    pages = []
    for name in [] if text else args.photos:
        data = Path(name).read_bytes()
        pages.append(PageImage(data, media_type(data, Path(name))))

    result = asyncio.run(analyze(pages, text, args.provider))
    report(result, args.seed, out)
    if args.json:
        Path(args.json).write_text(
            json.dumps(to_json(result), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0 if result.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
