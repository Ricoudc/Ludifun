"""Rapport des tests en famille (étape 18) : ce que disent les séances, les leçons et les avis.

    uv run python -m app.tools.pilot_report                       # 14 derniers jours
    uv run python -m app.tools.pilot_report --since 2026-10-01 --out ../eval/results/pilot.md

Aucune donnée nominative : les enfants sont numérotés (« Enfant 1, CM1 »), aucun texte de leçon
n'est repris. Seuls les messages que les parents ont écrits dans « Donner mon avis » sont cités.
Les critères de passage viennent du cahier des charges V1 (§17.3) et de la spécification
technique (§9, étape 18).
"""

import argparse
import asyncio
import statistics
import sys
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.pricing import worst_case_cost
from app.config import get_settings
from app.db import models as db
from app.db.base import Database
from app.domain.errors import ERROR_LABELS, ErrorType
from app.domain.understanding import MasteryLevel, notion_level
from app.services.dashboard import answer_seconds
from app.services.lesson_store import to_mastery

WITHOUT_HELP_TARGET = 0.8  # 4 enfants sur 5 finissent la séance sans aide (§17.3)
COMPLETION_TARGET = 0.8


@dataclass
class ChildStats:
    label: str
    sessions: int = 0
    completed: int = 0
    without_help: int = 0  # séances terminées sans « Je n'ai pas compris »
    minutes: float = 0.0
    scores: list[float] = field(default_factory=list)
    ratings: list[int] = field(default_factory=list)

    @property
    def average_score(self) -> float | None:
        return statistics.mean(self.scores) if self.scores else None


@dataclass
class PilotReport:
    since: date
    until: date
    families: int = 0
    children: list[ChildStats] = field(default_factory=list)
    sessions: int = 0
    completed: int = 0
    abandoned: int = 0
    completed_without_help: int = 0
    session_minutes: list[float] = field(default_factory=list)
    estimated_minutes: list[float] = field(default_factory=list)
    answers: int = 0
    help_requests: int = 0
    remediations: int = 0
    pauses_offered: int = 0
    bonus_taken: int = 0
    open_questions: int = 0
    errors: Counter[str] = field(default_factory=Counter)
    lessons: int = 0
    lessons_by_source: Counter[str] = field(default_factory=Counter)
    lessons_ready: int = 0
    failures: Counter[str] = field(default_factory=Counter)
    awaiting_review: int = 0
    analysis_seconds: list[float] = field(default_factory=list)
    ai_cost: float = 0.0
    cost_per_lesson: list[float] = field(default_factory=list)
    evaluations: Counter[str] = field(default_factory=Counter)
    notions_practised: int = 0
    notions_mastered: int = 0
    child_ratings: list[int] = field(default_factory=list)
    parent_ratings: list[int] = field(default_factory=list)
    parent_messages: list[tuple[datetime, int | None, str]] = field(default_factory=list)


def _start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


async def collect(session: AsyncSession, since: date, until: date) -> PilotReport:
    """Indicateurs sur la période [since, until] (jours UTC inclus)."""
    report = PilotReport(since, until)
    start, end = _start(since), _start(until + timedelta(days=1))
    in_period = db.RevisionSession.started_at.between(start, end)

    children = {c.id: c for c in await session.scalars(select(db.Child).order_by(db.Child.created_at))}
    stats: dict[uuid.UUID, ChildStats] = {}
    revisions = list(await session.scalars(select(db.RevisionSession).where(in_period)))
    for revision in revisions:
        child = children.get(revision.child_id)
        if child is None:
            continue
        per_child = stats.setdefault(child.id, ChildStats(""))
        items = list(
            await session.scalars(select(db.SessionItem).where(db.SessionItem.session_id == revision.id))
        )
        attempts = {
            a.session_item_id: a
            for a in await session.scalars(
                select(db.Attempt).where(db.Attempt.session_item_id.in_([i.id for i in items]))
            )
        }
        answered = [i for i in items if i.id in attempts and attempts[i.id].response != {"skipped": True}]
        helped = sum(1 for i in answered if i.help_level > 0)
        report.sessions += 1
        per_child.sessions += 1
        report.answers += len(answered)
        report.help_requests += helped
        report.remediations += 1 if any(i.block == "remediation" for i in items) else 0
        report.pauses_offered += 1 if revision.hint_at_answer is not None else 0
        report.bonus_taken += 1 if revision.extended else 0
        report.open_questions += sum(1 for i in answered if i.activity_type == "OPEN_QUESTION")
        minutes = sum(answer_seconds(attempts[i.id].duration_ms) for i in answered) / 60
        if revision.status == "completed":
            report.completed += 1
            per_child.completed += 1
            report.session_minutes.append(minutes)
            report.estimated_minutes.append(revision.estimated_duration_s / 60)
            per_child.minutes += minutes
            if revision.score_on_10 is not None:
                per_child.scores.append(float(revision.score_on_10))
            if helped == 0:
                report.completed_without_help += 1
                per_child.without_help += 1
        elif revision.status == "abandoned":
            report.abandoned += 1

    errors = await session.execute(
        select(db.AttemptEvidence.error_type)
        .join(db.Attempt, db.Attempt.id == db.AttemptEvidence.attempt_id)
        .where(db.Attempt.created_at.between(start, end), db.AttemptEvidence.error_type.is_not(None))
    )
    report.errors.update(error for (error,) in errors if error)

    lessons = list(await session.scalars(select(db.Lesson).where(db.Lesson.created_at.between(start, end))))
    report.lessons = len(lessons)
    for lesson in lessons:
        report.lessons_by_source[lesson.source] += 1
        if lesson.status == "ready":
            report.lessons_ready += 1
        elif lesson.status == "failed":
            report.failures[lesson.failure_reason or "?"] += 1
        elif lesson.status == "needs_review":
            report.awaiting_review += 1

    runs = list(await session.scalars(select(db.AiRun).where(db.AiRun.created_at.between(start, end))))
    per_lesson_cost: dict[uuid.UUID, float] = defaultdict(float)
    per_lesson_ms: dict[uuid.UUID, int] = defaultdict(int)
    for run in runs:
        cost = worst_case_cost(run.model, run.input_tokens, run.output_tokens)
        report.ai_cost += cost
        if run.stage == "evaluation":
            report.evaluations[run.status] += 1
        elif run.lesson_id is not None:
            per_lesson_cost[run.lesson_id] += cost
            per_lesson_ms[run.lesson_id] += run.latency_ms
    ready_ids = {lesson.id for lesson in lessons if lesson.status == "ready"}
    report.cost_per_lesson = [c for lesson_id, c in per_lesson_cost.items() if lesson_id in ready_ids]
    report.analysis_seconds = [ms / 1000 for lesson_id, ms in per_lesson_ms.items() if lesson_id in ready_ids]

    for mastery, item in (
        await session.execute(
            select(db.KnowledgeMastery, db.KnowledgeItem).join(
                db.KnowledgeItem, db.KnowledgeItem.id == db.KnowledgeMastery.knowledge_id
            )
        )
    ).all():
        report.notions_practised += 1
        if notion_level(to_mastery(mastery), item.required_levels).level >= MasteryLevel.MASTERED:
            report.notions_mastered += 1

    for feedback in await session.scalars(
        select(db.Feedback).where(db.Feedback.created_at.between(start, end)).order_by(db.Feedback.created_at)
    ):
        if feedback.author == "child":
            if feedback.rating is not None:
                report.child_ratings.append(feedback.rating)
                if feedback.child_id in stats:
                    stats[feedback.child_id].ratings.append(feedback.rating)
        else:
            if feedback.rating is not None:
                report.parent_ratings.append(feedback.rating)
            if feedback.message:
                report.parent_messages.append((feedback.created_at, feedback.rating, feedback.message))

    active_families = {children[c].family_id for c in stats}
    report.families = len(active_families)
    for number, (child_id, per_child) in enumerate(stats.items(), start=1):
        per_child.label = f"Enfant {number} ({children[child_id].grade})"
        report.children.append(per_child)
    return report


def _pct(part: int, total: int) -> str:
    return f"{100 * part / total:.0f} %" if total else "–"


def _median(values: list[float], unit: str = "", digits: int = 1) -> str:
    return f"{statistics.median(values):.{digits}f}{unit}" if values else "–"


def _mean(values: list[int]) -> str:
    return f"{statistics.mean(values):.1f} / 5 ({len(values)})" if values else "–"


def _check(ok: bool | None) -> str:
    return "–" if ok is None else "✅" if ok else "❌"


def render(report: PilotReport) -> str:
    r = report
    kids_ok = sum(
        1 for c in r.children if c.completed and c.without_help / c.completed >= WITHOUT_HELP_TARGET
    )
    kids_pass = kids_ok >= WITHOUT_HELP_TARGET * len(r.children) if r.children else None
    completion = r.completed / r.sessions if r.sessions else None
    lines = [
        f"# Tests en famille : du {r.since:%d/%m/%Y} au {r.until:%d/%m/%Y}",
        "",
        f"{r.families} famille(s), {len(r.children)} enfant(s) actif(s), {r.sessions} séance(s).",
        "",
        "## Critères de passage",
        "",
        "| Critère | Mesure | Seuil | |",
        "|---|---|---|---|",
        "| Enfants qui finissent leurs séances sans aide (≥ 80 % des séances) "
        f"| {kids_ok} / {len(r.children)} | 4 sur 5 | {_check(kids_pass)} |",
        f"| Séances terminées | {_pct(r.completed, r.sessions)} | ≥ 80 % "
        f"| {_check(completion >= COMPLETION_TARGET if completion is not None else None)} |",
        f"| Leçons analysées sans échec | {_pct(r.lessons_ready, r.lessons)} | ≥ 90 % "
        f"| {_check(r.lessons_ready >= 0.9 * r.lessons if r.lessons else None)} |",
        f"| Avis des enfants | {_mean(r.child_ratings)} | ≥ 4 / 5 "
        f"| {_check(statistics.mean(r.child_ratings) >= 4 if r.child_ratings else None)} |",
        f"| Avis des parents | {_mean(r.parent_ratings)} | ≥ 4 / 5 "
        f"| {_check(statistics.mean(r.parent_ratings) >= 4 if r.parent_ratings else None)} |",
        "",
        "Pertinence et justesse du contenu (§17.3) : grille `eval/grille-evaluation.md`, remplie à la main.",
        "",
        "## Par enfant",
        "",
        "| Enfant | Séances | Terminées | Sans aide | Minutes | Note moyenne | Avis |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in r.children:
        average = f"{c.average_score:.1f} / 10" if c.average_score is not None else "–"
        lines.append(
            f"| {c.label} | {c.sessions} | {c.completed} | {c.without_help} | {c.minutes:.0f} | {average} "
            f"| {_mean(c.ratings)} |"
        )
    top_errors = ", ".join(
        f"{ERROR_LABELS[ErrorType(e)].lower()} {n}" for e, n in r.errors.most_common(5) if e in ErrorType
    )
    lines += [
        "",
        "## Séances",
        "",
        f"- Terminées : {r.completed} ; abandonnées : {r.abandoned} ; sans aide : "
        f"{_pct(r.completed_without_help, r.completed)} des terminées.",
        f"- Durée médiane : {_median(r.session_minutes, ' min')} "
        f"(prévue : {_median(r.estimated_minutes, ' min')}).",
        f"- « Je n'ai pas compris » : {_pct(r.help_requests, r.answers)} des activités ; "
        f"questions ouvertes : {r.open_questions}.",
        f"- Remédiations : {r.remediations} séance(s) ; pauses proposées : {r.pauses_offered} ; "
        f"défis bonus acceptés : {r.bonus_taken}.",
        f"- Erreurs les plus fréquentes : {top_errors or '–'}.",
        "",
        "## Leçons et IA",
        "",
        f"- Leçons : {r.lessons} ({', '.join(f'{s} {n}' for s, n in r.lessons_by_source.items()) or '–'}) ; "
        f"prêtes : {r.lessons_ready} ; en attente de vérification : {r.awaiting_review}.",
        f"- Échecs : {', '.join(f'{k} {n}' for k, n in r.failures.most_common()) or 'aucun'}.",
        f"- Temps d'IA par leçon (médiane) : {_median(r.analysis_seconds, ' s', 0)} ; "
        f"coût par leçon (médiane) : {_median(r.cost_per_lesson, ' $', 3)} ; coût total : {r.ai_cost:.2f} $.",
        f"- Corrections de réponses rédigées : {r.evaluations.get('ok', 0)} par l'IA, "
        f"{sum(n for s, n in r.evaluations.items() if s != 'ok')} par mots clés.",
        f"- Notions travaillées : {r.notions_practised} ; maîtrisées (niveau 4 ou 5) : "
        f"{_pct(r.notions_mastered, r.notions_practised)}.",
        "",
        "## Messages des parents",
        "",
    ]
    lines += [
        f"- {at:%d/%m} {'★' * rating if rating else ''} « {message} »"
        for at, rating, message in r.parent_messages
    ] or ["Aucun message."]
    return "\n".join(lines) + "\n"


async def run(since: date, until: date) -> str:
    database = Database(get_settings().database_url)
    try:
        async with database.sessionmaker() as session:
            return render(await collect(session, since, until))
    finally:
        await database.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    today = datetime.now(UTC).date()
    parser.add_argument("--since", type=date.fromisoformat, default=today - timedelta(days=13))
    parser.add_argument("--until", type=date.fromisoformat, default=today)
    parser.add_argument("--out", type=Path, help="fichier Markdown (sinon, affiché)")
    args = parser.parse_args(argv)
    text = asyncio.run(run(args.since, args.until))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"Rapport écrit dans {args.out}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
