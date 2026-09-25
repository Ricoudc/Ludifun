"""Espace parent : tableau de bord et historique d'un enfant (écrans P3 et P4)."""

import uuid
from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app import clock
from app.api.deps import AppSettings, CurrentParent, DbSession
from app.api.errors import ApiError
from app.api.v1.children import own_child
from app.api.v1.schemas_dashboard import (
    DashboardOut,
    ErrorCountOut,
    HistoryEntryOut,
    HistoryOut,
    LessonProgressOut,
    LevelOut,
    LevelRateOut,
    NotionProgressOut,
    NotionResultOut,
    RecurringErrorOut,
    SessionActivityOut,
    SessionDecisionOut,
    SessionDetailOut,
    SkillProgressOut,
    SkillsOut,
    SubjectOut,
    WeakNotionOut,
    WeekOut,
)
from app.db import models as db_models
from app.domain.decisions import describe
from app.domain.errors import ERROR_LABELS
from app.domain.knowledge import SkillVerb
from app.domain.state import facts_sentence
from app.domain.understanding import LEVEL_LABELS, LEVEL_NAMES, CognitiveLevel, MasteryLevel, level_color
from app.services import dashboard, export
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
