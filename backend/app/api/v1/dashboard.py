"""Espace parent : tableau de bord et historique d'un enfant (écrans P3 et P4)."""

import uuid
from datetime import datetime
from typing import Annotated, cast
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app import clock
from app.api.deps import AppSettings, CurrentParent, DbSession
from app.api.errors import ApiError
from app.api.v1.children import own_child
from app.api.v1.schemas_dashboard import (
    DashboardOut,
    ErrorCountOut,
    HelpRequestOut,
    HelpRequestsOut,
    HelpStepOut,
    HistoryEntryOut,
    HistoryOut,
    LessonProgressOut,
    LevelOut,
    LevelRateOut,
    MistakeOut,
    MistakesOut,
    NotionProgressOut,
    NotionResultOut,
    Outcome,
    ProgrammeCompetenceOut,
    ProgrammeDomainOut,
    ProgrammeNotionOut,
    ProgrammeOut,
    ProgrammeSubjectOut,
    QuestionReportOut,
    QuestionReportsOut,
    RecurringErrorOut,
    ReportReason,
    SessionActivityOut,
    SessionDecisionOut,
    SessionDetailOut,
    SkillProgressOut,
    SkillsOut,
    SubCompetenceOut,
    SubjectOut,
    WeakNotionOut,
    WeekOut,
)
from app.db import models as db_models
from app.domain import mistakes as mistakes_domain
from app.domain.activities.registry import default_registry
from app.domain.decisions import describe
from app.domain.errors import ERROR_LABELS
from app.domain.help import TITLES as HELP_TITLES
from app.domain.help import HelpKind
from app.domain.knowledge import SkillVerb
from app.domain.state import facts_sentence
from app.domain.understanding import LEVEL_LABELS, LEVEL_NAMES, CognitiveLevel, MasteryLevel, level_color
from app.services import dashboard, export
from app.services import programme as programme_service
from app.services.dashboard import WeekStats

router = APIRouter(tags=["espace parent"])


def week_out(week: WeekStats) -> WeekOut:
    return WeekOut(
        week_start=week.week_start,
        sessions=week.sessions,
        minutes=week.minutes,
        average_score=week.average_score,
    )


@router.get("/children/{child_id}/dashboard")
async def get_dashboard(
    child_id: uuid.UUID,
    parent: CurrentParent,
    db: DbSession,
    settings: AppSettings,
    weeks: Annotated[int, Query(ge=1, le=12, description="Semaines de progression affichées")] = 4,
) -> DashboardOut:
    """Écran P3 : cette semaine, réussite par matière, notions à renforcer, progression."""
    child = await own_child(db, parent, child_id)
    tz = ZoneInfo(settings.family_timezone)
    board = await dashboard.build_dashboard(db, child.id, clock.now(), weeks, tz)
    return DashboardOut(
        child_id=child.id,
        timezone=settings.family_timezone,
        this_week=week_out(board.this_week),
        lessons_added_this_week=board.lessons_added_this_week,
        help_this_week=board.help_this_week,
        reports_to_see=board.reports_to_see,
        summary=board.summary,
        activities_this_week=board.activities,
        subjects=[
            SubjectOut(subject=s.subject, mastery=s.mastery, color=s.color, notions=s.notions)
            for s in board.subjects
        ],
        to_strengthen=[
            WeakNotionOut(
                knowledge_id=n.knowledge_id,
                label=n.label,
                lesson_id=n.lesson_id,
                lesson_title=n.lesson_title,
                subject=n.subject,
                mastery=n.mastery,
                status=n.status,
                next_review_at=n.next_review_at,
                level=n.level,
                explanation=n.explanation,
            )
            for n in board.to_strengthen
        ],
        reviews_due=board.due_now,
        weeks=[week_out(w) for w in board.weeks],
        trend=board.trend,
        error_types=[
            ErrorCountOut(error_type=e.error_type, label=ERROR_LABELS[e.error_type], count=e.count)
            for e in board.error_types
        ],
        recurring_errors=[
            RecurringErrorOut(
                knowledge_id=r.knowledge_id,
                label=r.label,
                lesson_title=r.lesson_title,
                error_type=r.error_type,
                error_label=ERROR_LABELS[r.error_type],
                sessions=r.sessions,
                last_at=r.last_at,
            )
            for r in board.recurring_errors
        ],
    )


@router.get("/children/{child_id}/mistakes")
async def get_mistakes(
    child_id: uuid.UUID,
    parent: CurrentParent,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    before: Annotated[
        datetime | None, Query(description="Curseur : `next_before` de la page précédente")
    ] = None,
) -> MistakesOut:
    """Questions ratées, de la plus récente à la plus ancienne : question, réponse, bonne réponse."""
    child = await own_child(db, parent, child_id)
    rows = await dashboard.mistakes(db, child.id, limit, before)
    registry = default_registry()
    out: list[MistakeOut] = []
    for row in rows:
        described = mistakes_domain.describe(registry, row.activity, row.response)
        if described is None:
            continue
        out.append(
            MistakeOut(
                answered_at=row.answered_at,
                lesson_id=row.lesson_id,
                lesson_title=row.lesson_title,
                subject=row.subject,
                activity_type=row.activity.type,
                notions=row.notions,
                question=described.question,
                given=described.given,
                expected=described.expected,
                partial=row.score > 0,
            )
        )
    return MistakesOut(mistakes=out, next_before=rows[-1].answered_at if len(rows) == limit else None)


@router.get("/children/{child_id}/help-requests")
async def get_help_requests(
    child_id: uuid.UUID,
    parent: CurrentParent,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    before: Annotated[
        datetime | None, Query(description="Curseur : `next_before` de la page précédente")
    ] = None,
) -> HelpRequestsOut:
    """Quand l'enfant a demandé de l'aide (« Je n'ai pas compris »), de la plus récente à la plus
    ancienne : la question, les aides vues avec leur heure, et s'il a réussi ensuite."""
    child = await own_child(db, parent, child_id)
    rows = await dashboard.help_requests(db, child.id, limit, before)
    out = [
        HelpRequestOut(
            asked_at=row.asked_at,
            lesson_id=row.lesson_id,
            lesson_title=row.lesson_title,
            subject=row.subject,
            activity_type=row.activity.type,
            notions=row.notions,
            question=mistakes_domain.question_of(row.activity),
            steps=[
                HelpStepOut(level=level, kind=kind, title=HELP_TITLES[HelpKind(kind)], at=at)
                for level, kind, at in row.steps
            ],
            outcome="unanswered"
            if row.score is None
            else "right"
            if row.score >= 1
            else "partial"
            if row.score > 0
            else "wrong",
        )
        for row in rows
    ]
    return HelpRequestsOut(help_requests=out, next_before=rows[-1].asked_at if len(rows) == limit else None)


REPORT_LABELS = {
    "right_answer": "Ma réponse était juste",
    "unclear": "Je ne comprends pas la question",
    "wrong_question": "Il y a une erreur dans la question",
}


def _outcome(score: float | None) -> Outcome:
    if score is None:
        return "unanswered"
    return "right" if score >= 1 else "partial" if score > 0 else "wrong"


@router.get("/children/{child_id}/question-reports")
async def get_question_reports(
    child_id: uuid.UUID,
    parent: CurrentParent,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    before: Annotated[
        datetime | None, Query(description="Curseur : `next_before` de la page précédente")
    ] = None,
) -> QuestionReportsOut:
    """Questions signalées par l'enfant (🚩), de la plus récente à la plus ancienne : la raison
    choisie, la question telle qu'il l'a vue, sa réponse et celle retenue par Ludifun."""
    child = await own_child(db, parent, child_id)
    rows = await dashboard.question_reports(db, child.id, limit, before)
    registry = default_registry()
    out = []
    for row in rows:
        described = (
            mistakes_domain.describe(registry, row.activity, row.response)
            if row.response is not None
            else None
        )
        out.append(
            QuestionReportOut(
                id=row.id,
                reported_at=row.reported_at,
                reason=cast(ReportReason, row.reason),
                reason_label=REPORT_LABELS[row.reason],
                seen=row.seen_at is not None,
                lesson_id=row.lesson_id,
                lesson_title=row.lesson_title,
                subject=row.subject,
                activity_type=row.activity.type,
                notions=row.notions,
                question=mistakes_domain.question_of(row.activity),
                given=described.given if described else None,
                expected=described.expected if described else _display(row.activity.solution),
                outcome=_outcome(row.score),
            )
        )
    return QuestionReportsOut(reports=out, next_before=rows[-1].reported_at if len(rows) == limit else None)


def _display(solution: dict[str, object]) -> str | None:
    value = solution.get("display")
    return str(value) if value is not None else None


@router.post("/children/{child_id}/question-reports/{report_id}/seen", status_code=status.HTTP_204_NO_CONTENT)
async def mark_report_seen(
    child_id: uuid.UUID, report_id: uuid.UUID, parent: CurrentParent, db: DbSession
) -> Response:
    """Le parent a regardé la question signalée (et l'a corrigée s'il le fallait)."""
    child = await own_child(db, parent, child_id)
    report = await db.scalar(
        select(db_models.QuestionReport)
        .join(db_models.SessionItem, db_models.SessionItem.id == db_models.QuestionReport.session_item_id)
        .join(db_models.RevisionSession, db_models.RevisionSession.id == db_models.SessionItem.session_id)
        .where(db_models.QuestionReport.id == report_id, db_models.RevisionSession.child_id == child.id)
    )
    if report is None:
        raise ApiError(404, "report_not_found", "Signalement introuvable.")
    if report.seen_at is None:
        report.seen_at = clock.now()
        await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/children/{child_id}/history")
async def get_history(
    child_id: uuid.UUID,
    parent: CurrentParent,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    before: Annotated[
        datetime | None, Query(description="Curseur : `next_before` de la page précédente")
    ] = None,
) -> HistoryOut:
    """Écran P4 : séances de la plus récente à la plus ancienne."""
    child = await own_child(db, parent, child_id)
    entries = await dashboard.history(db, child.id, limit, before)
    return HistoryOut(
        sessions=[
            HistoryEntryOut(
                session_id=e.session_id,
                lesson_id=e.lesson_id,
                lesson_title=e.lesson_title,
                subject=e.subject,
                kind=e.kind,
                status=e.status,
                started_at=e.started_at,
                completed_at=e.completed_at,
                minutes=e.minutes,
                score_on_10=e.score_on_10,
                notions=[NotionResultOut(label=n.label, status=n.status) for n in e.notions],
            )
            for e in entries
        ],
        next_before=entries[-1].started_at if len(entries) == limit else None,
    )


def level_out(level: int) -> LevelOut:
    value = MasteryLevel(level)
    return LevelOut(value=value, label=LEVEL_LABELS[value], color=level_color(value))


def _notion_out(n: programme_service.PlacedNotion) -> ProgrammeNotionOut:
    return ProgrammeNotionOut(
        label=n.label, lesson_id=n.lesson_id, lesson_title=n.lesson_title, level=level_out(n.level)
    )


def _sub_out(s: programme_service.SubProgress) -> SubCompetenceOut:
    return SubCompetenceOut(
        id=s.sub.id,
        title=s.sub.title,
        grades=list(s.sub.grades),
        status=s.status,
        notions=[_notion_out(n) for n in s.notions],
    )


@router.get("/children/{child_id}/programme")
async def get_programme(child_id: uuid.UUID, parent: CurrentParent, db: DbSession) -> ProgrammeOut:
    """Le programme de la classe de l'enfant, matière par matière : chaque sous-compétence avec
    les notions de ses leçons qui s'y rattachent (rapprochement fait par le code) et son état."""
    child = await own_child(db, parent, child_id)
    progress = await programme_service.programme_progress(db, child)
    return ProgrammeOut(
        grade=progress.grade,
        version=progress.version,
        source=progress.source,
        subjects=[
            ProgrammeSubjectOut(
                subject=subject.subject,
                total=subject.total,
                started=subject.count("started"),
                mastered=subject.count("mastered"),
                domains=[
                    ProgrammeDomainOut(
                        title=d.title,
                        competences=[
                            ProgrammeCompetenceOut(title=c.title, subs=[_sub_out(s) for s in c.subs])
                            for c in d.competences
                        ],
                    )
                    for d in subject.domains
                ],
                elsewhere=[_sub_out(s) for s in subject.elsewhere],
                unplaced=[_notion_out(n) for n in subject.unplaced],
            )
            for subject in progress.subjects
        ],
    )


@router.get("/children/{child_id}/skills")
async def get_skills(child_id: uuid.UUID, parent: CurrentParent, db: DbSession) -> SkillsOut:
    """Compétences et notions de chaque leçon, avec leur niveau de 0 à 5 et ce qui manque encore."""
    child = await own_child(db, parent, child_id)
    lessons = await dashboard.lessons_progress(db, child.id, limit=20)
    return SkillsOut(
        lessons=[
            LessonProgressOut(
                lesson_id=lesson.lesson_id,
                title=lesson.title,
                subject=lesson.subject,
                created_at=lesson.created_at,
                skills=[
                    SkillProgressOut(
                        id=skill.skill_id,
                        label=skill.label,
                        verb=SkillVerb(skill.verb),
                        importance=skill.importance,
                        level=level_out(skill.level),
                        knowledge_ids=skill.knowledge_ids,
                    )
                    for skill in lesson.skills
                ],
                notions=[
                    NotionProgressOut(
                        id=notion.knowledge_id,
                        label=notion.label,
                        importance=notion.importance,
                        level=level_out(notion.level.level),
                        explanation=notion.level.explanation,
                        facts=facts_sentence(notion.state),
                        level_rates=[
                            LevelRateOut(level=level, name=LEVEL_NAMES[CognitiveLevel(level)], rate=rate)
                            for level, rate in notion.state.level_rates.items()
                        ],
                        independence=notion.state.independence,
                    )
                    for notion in lesson.notions
                ],
            )
            for lesson in lessons
        ]
    )


@router.get("/children/{child_id}/export")
async def export_child(child_id: uuid.UUID, parent: CurrentParent, db: DbSession) -> JSONResponse:
    """§16.2 : toutes les données de l'enfant, en un fichier JSON (droit d'accès et de portabilité)."""
    child = await own_child(db, parent, child_id)
    now = clock.now()
    data = await export.export_child(db, child, now)
    filename = f"ludifun-{child.id}-{now.date().isoformat()}.json"
    return JSONResponse(data, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


ACTIVITY_NAMES = {
    "MCQ": "QCM",
    "TRUE_FALSE": "Vrai ou faux",
    "FILL_BLANK": "Texte à trou",
    "MATCH": "Association",
    "SPEED_CHALLENGE": "Défi rapide",
    "FLASHCARD": "Carte mémoire",
    "OPEN_QUESTION": "Question rédigée",
    "ORDER": "Remettre dans l'ordre",
    "TIMELINE": "Frise chronologique",
    "CLASSIFY": "Ranger dans les cases",
    "MEMORY": "Memory",
    "MAP": "Carte",
    "COLORING": "Coloriage",
}


def _result(score: float, response: dict[str, object]) -> str:
    if response == {"skipped": True}:
        return "skipped"
    return "correct" if score >= 1 else "partial" if score >= 0.5 else "incorrect"


@router.get("/children/{child_id}/sessions/{session_id}")
async def get_session_detail(
    child_id: uuid.UUID, session_id: uuid.UUID, parent: CurrentParent, db: DbSession
) -> SessionDetailOut:
    """Pourquoi ces activités (CDC §126) : la raison de chaque choix du moteur, les résultats et les
    décisions prises pendant la séance (remédiation, pause, défis bonus)."""
    child = await own_child(db, parent, child_id)
    revision = await db.get(db_models.RevisionSession, session_id)
    if revision is None or revision.child_id != child.id:
        raise ApiError(404, "session_not_found", "Séance introuvable.")
    items = (
        await db.scalars(
            select(db_models.SessionItem)
            .where(db_models.SessionItem.session_id == revision.id)
            .order_by(db_models.SessionItem.position)
        )
    ).all()
    attempts = {
        a.session_item_id: a
        for a in await db.scalars(
            select(db_models.Attempt).where(db_models.Attempt.session_item_id.in_([i.id for i in items]))
        )
    }
    rows = await db.execute(
        select(db_models.KnowledgeItem.id, db_models.KnowledgeItem.label).where(
            db_models.KnowledgeItem.lesson_id == revision.lesson_id
        )
    )
    labels: dict[uuid.UUID, str] = {knowledge_id: label for knowledge_id, label in rows}
    return SessionDetailOut(
        session_id=revision.id,
        kind=revision.kind,
        started_at=revision.started_at,
        engine_version=revision.engine_version,
        activities=[
            SessionActivityOut(
                position=item.position,
                block=item.block,
                activity=ACTIVITY_NAMES.get(item.activity_type, item.activity_type),
                difficulty=item.difficulty,
                notions=[labels.get(k, "?") for k in item.knowledge_ids],
                result=(
                    _result(float(attempts[item.id].score), attempts[item.id].response)
                    if item.id in attempts
                    else None
                ),
                help_level=item.help_level,
                reason=describe(item.reason),
            )
            for item in items
        ],
        decisions=[
            SessionDecisionOut(
                rule=str(d.get("rule")), text=describe(d) or str(d.get("rule")), position=d.get("position")
            )
            for d in revision.decisions
        ],
    )
