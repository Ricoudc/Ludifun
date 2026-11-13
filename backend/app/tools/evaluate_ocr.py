"""Benchmark OCR local sur un corpus privé (aucune image ni transcription dans le rapport).

Exemple :
    uv run python -m app.tools.evaluate_ocr C:/chemin/ocr-private --output C:/temp/ocr-report.json

Chaque image doit avoir un fichier .txt de même nom contenant la transcription de référence.
Par défaut, seuls les modèles Ollama sont autorisés : --allow-remote est requis pour tout
autre fournisseur. Le rapport ne contient ni image, ni transcription, ni nom de fichier.
"""

import argparse
import asyncio
import json
import math
import re
import statistics
import unicodedata
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.ai.factory import build_providers
from app.ai.ocr.tesseract import TesseractOcr
from app.ai.ocr.vision_llm import VisionLLMOcr
from app.ai.ports import AIError, OcrProvider, PageImage
from app.config import Settings

IMAGE_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
CRITICAL_TOKEN = re.compile(
    r"°c|%|\b(?:km|cm|mm|kg|mg|ml|cl|g|l|m|h|min|s)\b|\d+(?:[.,]\d+)?|[=+\-×÷<>≤≥≠≈√]"
)


def normalize_text(value: str) -> str:
    """Normalise Unicode et espaces, sans modifier chiffres, signes ou ponctuation."""
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def edit_distance(reference: Sequence[str], actual: Sequence[str]) -> int:
    """Distance de Levenshtein avec mémoire O(min(n, m))."""
    if len(reference) < len(actual):
        reference, actual = actual, reference
    previous = list(range(len(actual) + 1))
    for i, expected in enumerate(reference, start=1):
        current = [i]
        for j, observed in enumerate(actual, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[j] + 1,
                    previous[j - 1] + (expected != observed),
                )
            )
        previous = current
    return previous[-1]


def metrics(reference: str, actual: str) -> dict[str, int]:
    expected = normalize_text(reference)
    observed = normalize_text(actual)
    expected_words, observed_words = expected.split(), observed.split()
    expected_critical = CRITICAL_TOKEN.findall(expected)
    observed_critical = CRITICAL_TOKEN.findall(observed)
    return {
        "reference_chars": len(expected),
        "char_errors": edit_distance(list(expected), list(observed)),
        "reference_words": len(expected_words),
        "word_errors": edit_distance(expected_words, observed_words),
        "reference_critical_tokens": len(expected_critical),
        "critical_token_errors": edit_distance(expected_critical, observed_critical),
    }


def _rate(errors: int, total: int) -> float | None:
    return round(errors / total, 4) if total else None


def _percentile(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    totals = {
        key: sum(int(row["metrics"][key]) for row in rows)
        for key in (
            "reference_chars",
            "char_errors",
            "reference_words",
            "word_errors",
            "reference_critical_tokens",
            "critical_token_errors",
        )
    }
    latencies = [int(row["latency_ms"]) for row in rows if row["latency_ms"] is not None]
    return {
        "pages": len(rows),
        "cer": _rate(totals["char_errors"], totals["reference_chars"]),
        "wer": _rate(totals["word_errors"], totals["reference_words"]),
        "critical_token_error_rate": _rate(
            totals["critical_token_errors"], totals["reference_critical_tokens"]
        ),
        "latency_ms_median": int(statistics.median(latencies)) if latencies else None,
        "latency_ms_p95": _percentile(latencies, 0.95),
        "errors": sum(row["error"] is not None for row in rows),
    }


async def evaluate(corpus: Path, output: Path, allow_remote: bool) -> dict[str, Any]:
    settings = Settings()
    if settings.ai_provider != "ollama" and not allow_remote:
        raise SystemExit(
            "Par défaut, ce benchmark n'envoie aucune photo à un fournisseur distant. "
            "Configurez LUDIFUN_AI_PROVIDER=ollama ou ajoutez explicitement --allow-remote."
        )
    if settings.ai_provider == "fake":
        raise SystemExit("Le fournisseur fake ne peut pas lire les photos : configurez Ollama.")

    images = sorted(
        path for path in corpus.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_TYPES
    )
    pairs = [(path, path.with_suffix(".txt")) for path in images]
    missing = [str(image.name) for image, truth in pairs if not truth.is_file()]
    if not images or missing:
        raise SystemExit(
            "Corpus vide ou transcriptions manquantes (.txt de même nom) : "
            + (", ".join(missing[:10]) if missing else str(corpus))
        )

    auto_settings = settings.model_copy(update={"ocr_engine": "auto"})
    auto_reader, llm = build_providers(auto_settings)
    readers: dict[str, OcrProvider] = {
        "tesseract": TesseractOcr(settings.tesseract_cmd, settings.tesseract_languages),
        "vision": VisionLLMOcr(llm),
        "auto": auto_reader,
    }
    rows: dict[str, list[dict[str, Any]]] = {name: [] for name in readers}
    try:
        for index, (image_path, truth_path) in enumerate(pairs, start=1):
            page = PageImage(image_path.read_bytes(), IMAGE_TYPES[image_path.suffix.lower()])
            reference = truth_path.read_text(encoding="utf-8")
            for name, reader in readers.items():
                try:
                    result = await reader.extract((page,))
                    actual = result.output.pages[0].text if result.output.pages else ""
                    rows[name].append(
                        {
                            "page": index,
                            "metrics": metrics(reference, actual),
                            "latency_ms": result.usage.latency_ms,
                            "model": result.usage.model,
                            "error": None,
                        }
                    )
                except (AIError, OSError, ValueError) as exc:
                    rows[name].append(
                        {
                            "page": index,
                            "metrics": metrics(reference, ""),
                            "latency_ms": None,
                            "model": reader.model,
                            "error": type(exc).__name__,
                        }
                    )
    finally:
        client = getattr(llm, "_client", None)
        if client is not None:
            await client.aclose()

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": settings.ai_provider,
        "models": {
            name: next((row["model"] for row in values if row["model"]), "unknown")
            for name, values in rows.items()
        },
        "corpus_pages": len(images),
        "privacy": "Aucune image, transcription ou nom de fichier dans ce rapport.",
        "results": {
            name: {"summary": _summary(values), "pages": values} for name, values in rows.items()
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Tesseract, vision et OCR auto.")
    parser.add_argument("corpus", type=Path, help="Dossier privé d'images + fichiers .txt de référence")
    parser.add_argument("--output", type=Path, default=Path("ocr-benchmark-report.json"))
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Autorise explicitement l'envoi des photos au fournisseur configuré hors Ollama.",
    )
    args = parser.parse_args()
    report = asyncio.run(evaluate(args.corpus, args.output, args.allow_remote))
    print(f"Rapport agrégé écrit dans : {args.output}")
    for name, result in report["results"].items():
        summary = result["summary"]
        print(
            f"{name:10} CER={summary['cer']} WER={summary['wer']} "
            f"tokens_critiques={summary['critical_token_error_rate']} "
            f"p50={summary['latency_ms_median']} ms p95={summary['latency_ms_p95']} ms"
        )


if __name__ == "__main__":
    main()
