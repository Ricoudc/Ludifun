"""Espace parent : tableau de bord et historique d'un enfant (écrans P3 et P4)."""

import uuid
from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app import clock
from app.api.deps import AppSettings, CurrentParent, DbSession
from app.api.v1.children import own_child
from app.api.v1.schemas_dashboard import (
    DashboardOut,
    HistoryEntryOut,
    HistoryOut,
    NotionResultOut,
    SubjectOut,
    WeakNotionOut,
    WeekOut,
)
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
            )
            for n in board.to_strengthen
        ],
        reviews_due=board.due_now,
        weeks=[week_out(w) for w in board.weeks],
        trend=board.trend,
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


@router.get("/children/{child_id}/export")
async def export_child(child_id: uuid.UUID, parent: CurrentParent, db: DbSession) -> JSONResponse:
    """§16.2 : toutes les données de l'enfant, en un fichier JSON (droit d'accès et de portabilité)."""
    child = await own_child(db, parent, child_id)
    now = clock.now()
    data = await export.export_child(db, child, now)
    filename = f"ludifun-{child.id}-{now.date().isoformat()}.json"
    return JSONResponse(data, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
