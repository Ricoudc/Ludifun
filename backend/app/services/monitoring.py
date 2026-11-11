"""Suivi de l'IA : page `/suivi` (en direct) et le rapport de `Ludifun.bat` (choix 10) (texte à partager).

Uniquement des données techniques : étapes, modèles, durées, statuts et erreurs. Ni prénom, ni
titre ou texte de leçon, ni clé d'API ; une leçon est désignée par le début de son identifiant.
"""

import re
import statistics
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.pricing import run_cost
from app.db.models import (
    AiRun,
    FamilyAiSettings,
    KnowledgeItem,
    KnowledgeMaterial,
    Lesson,
    QuestionReport,
    RevisionSession,
    SessionItem,
)
from app.services.lesson_pipeline import STAGE_LABELS
from app.services.lesson_processing import IN_PROGRESS
from app.services.live_calls import LiveCall, LiveCalls

# Étapes qui produisent des exercices : leurs avertissements « élément : raison » sont des
# éléments écartés par les contrôles du code (§5.80).
EXERCISE_STAGES = frozenset({"material", "practice", "targeted"})
RECENT_LESSONS = 15
RECENT_ERRORS = 15
STATS_DAYS = 7
MESSAGE_MAX = 200
NOTES_PER_STEP = 5
# Une erreur de validation cite la réponse de l'IA (« input_value=… ») : elle peut contenir le
# texte de la leçon. On l'enlève.
_INPUT = re.compile(r"input_value=.*?(?=, input_type=|$)", re.DOTALL)


STATUS_LABELS = {
    "uploaded": "reçue",
    "reading": "lecture",
    "analyzing": "analyse",
    "generating": "exercices",
    "needs_review": "à vérifier par l'enfant",
    "ready": "prête",
    "failed": "échec",
}


def short(lesson_id: uuid.UUID | None) -> str:
    return str(lesson_id)[:8] if lesson_id else "—"


def clean_message(text: str) -> str:
    text = _INPUT.sub("input_value=…", text)
    return text if len(text) <= MESSAGE_MAX else text[: MESSAGE_MAX - 1] + "…"


def _cost(runs: list[AiRun]) -> float | None:
    """Coût en dollars (prix publics, `app.ai.pricing`) ; None si un modèle est inconnu."""
    costs = [run_cost(r.model, r.input_tokens, r.output_tokens) for r in runs]
    return None if any(c is None for c in costs) else round(sum(c or 0 for c in costs), 4)


def _rejected(runs: list[AiRun]) -> int:
    return sum(
        1
        for r in runs
        if r.stage in EXERCISE_STAGES
        for w in r.warnings
        if " : " in str(w) and not str(w).startswith("taux de rejet")
    )


async def _quality(db: AsyncSession, lesson_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:
    """Par leçon : notions gardées, questions à choix, questions signalées par l'enfant (§5.80)."""
    found: dict[uuid.UUID, dict[str, int]] = {
        i: {"notions": 0, "questions": 0, "reports": 0} for i in lesson_ids
    }
    for lesson_id, material in await db.execute(
        select(KnowledgeItem.lesson_id, KnowledgeMaterial.material)
        .join(KnowledgeMaterial, KnowledgeMaterial.knowledge_id == KnowledgeItem.id)
        .where(KnowledgeItem.lesson_id.in_(lesson_ids), KnowledgeItem.removed_at.is_(None))
    ):
        found[lesson_id]["notions"] += 1
        found[lesson_id]["questions"] += len(material.get("questions", []))
    for lesson_id, count in await db.execute(
        select(RevisionSession.lesson_id, func.count(QuestionReport.id))
        .join(SessionItem, SessionItem.id == QuestionReport.session_item_id)
        .join(RevisionSession, RevisionSession.id == SessionItem.session_id)
        .where(RevisionSession.lesson_id.in_(lesson_ids))
        .group_by(RevisionSession.lesson_id)
    ):
        found[lesson_id]["reports"] = count
    return found


def _seconds(delta: timedelta) -> int:
    return max(0, round(delta.total_seconds()))


def _p95_ms(latencies: list[int]) -> int:
    """Percentile 95 au rang le plus proche : stable même avec peu d'appels."""
    if not latencies:
        return 0
    ordered = sorted(latencies)
    rank = max(1, (95 * len(ordered) + 99) // 100)
    return ordered[rank - 1]


async def snapshot(db: AsyncSession, now: datetime, server_ai: str, live: LiveCalls) -> dict[str, Any]:
    running = (
        await db.scalars(select(Lesson).where(Lesson.status.in_(IN_PROGRESS)).order_by(Lesson.created_at))
    ).all()
    calls_by_lesson: dict[uuid.UUID | None, list[LiveCall]] = defaultdict(list)
    for call in live.current():
        calls_by_lesson[call.lesson_id].append(call)

    recent = (await db.scalars(select(Lesson).order_by(Lesson.created_at.desc()).limit(RECENT_LESSONS))).all()
    runs = (
        await db.scalars(
            select(AiRun)
            .where(AiRun.lesson_id.in_([lesson.id for lesson in recent]))
            .order_by(AiRun.created_at)
        )
    ).all()
    runs_by_lesson: dict[uuid.UUID | None, list[AiRun]] = defaultdict(list)
    for run in runs:
        runs_by_lesson[run.lesson_id].append(run)

    since = now - timedelta(days=STATS_DAYS)
    week = (await db.scalars(select(AiRun).where(AiRun.created_at >= since))).all()
    grouped: dict[tuple[str, str], list[AiRun]] = defaultdict(list)
    for run in week:
        grouped[(run.model, run.stage)].append(run)

    quality = await _quality(db, [lesson.id for lesson in recent])
    analysed = {r.lesson_id for r in week if r.lesson_id is not None}
    week_cost = _cost(list(week))
    errors = (
        await db.scalars(
            select(AiRun).where(AiRun.status != "ok").order_by(AiRun.created_at.desc()).limit(RECENT_ERRORS)
        )
    ).all()
    families = (
        await db.execute(select(FamilyAiSettings.provider, func.count()).group_by(FamilyAiSettings.provider))
    ).all()

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "server_ai": server_ai,
        "family_ai": {provider: count for provider, count in families},
        "running": [
            {
                "lesson": short(lesson.id),
                "status": STATUS_LABELS.get(lesson.status, lesson.status),
                "source": lesson.source,
                "pages": lesson.page_count,
                "elapsed_s": _seconds(now - lesson.created_at),
                "calls": [
                    {
                        "stage": STAGE_LABELS.get(call.stage, call.stage),  # type: ignore[call-overload]
                        "model": call.model,
                        "elapsed_s": _seconds(now - call.started_at),
                    }
                    for call in calls_by_lesson.get(lesson.id, [])
                ],
            }
            for lesson in running
        ],
        "recent": [
            {
                "lesson": short(lesson.id),
                "created_at": lesson.created_at.isoformat(timespec="seconds"),
                "state": lesson.status,
                "status": STATUS_LABELS.get(lesson.status, lesson.status),
                "failure": lesson.failure_reason,
                "source": lesson.source,
                "pages": lesson.page_count,
                "subject": lesson.subject,
                "ai_s": round(sum(r.latency_ms for r in runs_by_lesson.get(lesson.id, [])) / 1000),
                # Coût et qualité des exercices (§5.80) : des chiffres, jamais le texte.
                "cost_usd": _cost(runs_by_lesson.get(lesson.id, [])),
                "exercises": {
                    **quality[lesson.id],
                    "rejected": _rejected(runs_by_lesson.get(lesson.id, [])),
                },
                "steps": [
                    {
                        "stage": STAGE_LABELS.get(run.stage, run.stage),  # type: ignore[call-overload]
                        "model": run.model,
                        "seconds": round(run.latency_ms / 1000),
                        "status": run.status,
                        "tokens": [run.input_tokens, run.output_tokens],
                        # Avertissements techniques (notions écartées et pourquoi, jamais le texte).
                        "notes": [clean_message(str(w)) for w in run.warnings[:NOTES_PER_STEP]],
                    }
                    for run in runs_by_lesson.get(lesson.id, [])
                ],
            }
            for lesson in recent
        ],
        "stats": [
            {
                "model": model,
                "stage": STAGE_LABELS.get(stage, stage),  # type: ignore[call-overload]
                "calls": len(group),
                "ok": sum(1 for r in group if r.status == "ok"),
                "median_s": round(statistics.median(r.latency_ms for r in group) / 1000),
                "p95_s": round(_p95_ms([r.latency_ms for r in group]) / 1000),
                "max_s": round(max(r.latency_ms for r in group) / 1000),
                "input_tokens": sum(r.input_tokens or 0 for r in group),
                "output_tokens": sum(r.output_tokens or 0 for r in group),
                # Débit de bout en bout, pas le débit de génération GPU : inclut chargement et lecture.
                "output_tokens_per_s": _output_tokens_per_s(group),
                "cost_usd": _cost(group),
            }
            for (model, stage), group in sorted(grouped.items())
        ],
        "cost": {
            "week_usd": week_cost,
            "lessons": len(analysed),
            "per_lesson_usd": (
                round(week_cost / len(analysed), 4) if week_cost is not None and analysed else None
            ),
        },
        "errors": [
            {
                "at": run.created_at.isoformat(timespec="seconds"),
                "lesson": short(run.lesson_id),
                "stage": STAGE_LABELS.get(run.stage, run.stage),  # type: ignore[call-overload]
                "model": run.model,
                "status": run.status,
                "message": clean_message(str(run.warnings[0])) if run.warnings else "",
            }
            for run in errors
        ],
    }


def _output_tokens_per_s(runs: list[AiRun]) -> float | None:
    """Jetons de sortie par seconde de latence totale, uniquement pour les appels réussis."""
    measured = [r for r in runs if r.status == "ok" and r.output_tokens and r.latency_ms > 0]
    elapsed_ms = sum(r.latency_ms for r in measured)
    return round(sum(r.output_tokens or 0 for r in measured) * 1000 / elapsed_ms, 1) if elapsed_ms else None


def _dollars(value: float | None) -> str:
    return "?" if value is None else f"{value:.4f} $"


def as_text(data: dict[str, Any]) -> str:
    """Le même contenu, en texte simple (Ludifun.bat, choix 10)."""
    lines = [
        f"Rapport du {data['generated_at']}",
        f"IA du serveur : {data['server_ai']}",
        "IA choisies par les familles : "
        + (", ".join(f"{p} ({n})" for p, n in data["family_ai"].items()) or "aucune (IA du serveur)"),
        "",
        "== Analyses en cours ==",
    ]
    for lesson in data["running"]:
        lines.append(
            f"- {lesson['lesson']} · {lesson['status']} · {lesson['source']}, {lesson['pages']} page(s)"
            f" · depuis {lesson['elapsed_s']} s"
        )
        lines += [
            f"    en cours : {c['stage']} ({c['model']}) depuis {c['elapsed_s']} s" for c in lesson["calls"]
        ]
    if not data["running"]:
        lines.append("aucune")
    lines += ["", "== Dernières leçons =="]
    for lesson in data["recent"]:
        failure = f" ({lesson['failure']})" if lesson["failure"] else ""
        lines.append(
            f"- {lesson['created_at']} · {lesson['lesson']} · {lesson['status']}{failure} · "
            f"{lesson['source']}, {lesson['pages']} page(s) · {lesson['subject'] or '?'} · "
            f"IA {lesson['ai_s']} s · coût {_dollars(lesson['cost_usd'])}"
        )
        q = lesson["exercises"]
        lines.append(
            f"    exercices : {q['notions']} notion(s), {q['questions']} question(s), "
            f"{q['rejected']} écarté(s) par les contrôles, {q['reports']} signalée(s)"
        )
        for s in lesson["steps"]:
            lines.append(
                f"    {s['stage']} : {s['seconds']} s, {s['status']} ({s['model']}, "
                f"jetons {s['tokens'][0]}/{s['tokens'][1]})"
            )
            lines += [f"      · {note}" for note in s["notes"]]
    lines += ["", f"== Durées par modèle ({STATS_DAYS} derniers jours) =="]
    lines += [
        f"- {s['model']} · {s['stage']} : {s['ok']}/{s['calls']} réussis, "
        f"médiane {s['median_s']} s, p95 {s['p95_s']} s, max {s['max_s']} s, "
        f"{s['output_tokens']} jetons sortants à {s['output_tokens_per_s'] or '?'} jetons/s (temps total), "
        f"coût {_dollars(s['cost_usd'])}"
        for s in data["stats"]
    ] or ["aucun appel"]
    cost = data["cost"]
    lines.append(
        f"Coût sur {STATS_DAYS} jours : {_dollars(cost['week_usd'])} pour {cost['lessons']} leçon(s), "
        f"soit {_dollars(cost['per_lesson_usd'])} par leçon"
    )
    lines += ["", "== Dernières erreurs de l'IA =="]
    lines += [
        f"- {e['at']} · {e['lesson']} · {e['stage']} ({e['model']}) · {e['status']} : {e['message']}"
        for e in data["errors"]
    ] or ["aucune"]
    return "\n".join(lines)
