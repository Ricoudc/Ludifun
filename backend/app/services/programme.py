"""Le programme de la classe de l'enfant (§105) : pour chaque sous-compétence, les notions de ses
leçons qui s'y rattachent et leur niveau ; ce qui est maîtrisé, commencé, ou pas encore vu."""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as db
from app.domain.knowledge import Subject
from app.domain.programme import Programme, SubCompetence, load_programme, place
from app.domain.understanding import MasteryLevel, notion_level
from app.services.lesson_store import to_mastery

Status = Literal["not_seen", "started", "mastered"]


@dataclass(frozen=True)
class PlacedNotion:
    label: str
    lesson_id: uuid.UUID
    lesson_title: str | None
    level: int  # 0 à 5


@dataclass
class SubProgress:
    sub: SubCompetence
    notions: list[PlacedNotion] = field(default_factory=list)

    @property
    def status(self) -> Status:
        if not self.notions:
            return "not_seen"
        if all(n.level >= MasteryLevel.MASTERED for n in self.notions):
            return "mastered"
        return "started"


@dataclass(frozen=True)
class CompetenceProgress:
    title: str
    subs: list[SubProgress]


@dataclass(frozen=True)
class DomainProgress:
    title: str
    competences: list[CompetenceProgress]


@dataclass(frozen=True)
class SubjectProgress:
    subject: str
    domains: list[DomainProgress]
    elsewhere: list[SubProgress]  # notions d'un autre niveau (une leçon de CE2 revue en CM1)
    unplaced: list[PlacedNotion]  # hors du référentiel

    def count(self, status: Status) -> int:
        return sum(1 for d in self.domains for c in d.competences for s in c.subs if s.status == status)

    @property
    def total(self) -> int:
        return sum(len(c.subs) for d in self.domains for c in d.competences)


@dataclass(frozen=True)
class ProgrammeProgress:
    grade: str
    version: str
    source: str
    subjects: list[SubjectProgress]


async def programme_progress(
    session: AsyncSession, child: db.Child, programme: Programme | None = None
) -> ProgrammeProgress:
    programme = programme or load_programme()
    masteries = {
        m.knowledge_id: m
        for m in await session.scalars(
            select(db.KnowledgeMastery).where(db.KnowledgeMastery.child_id == child.id)
        )
    }
    rows = await session.execute(
        select(db.KnowledgeItem, db.Lesson)
        .join(db.Lesson, db.Lesson.id == db.KnowledgeItem.lesson_id)
        .where(db.Lesson.child_id == child.id, db.Lesson.status == "ready")
        .order_by(db.Lesson.created_at, db.KnowledgeItem.position)
    )
    placed: dict[str, list[PlacedNotion]] = defaultdict(list)
    elsewhere: dict[str, list[PlacedNotion]] = defaultdict(list)
    unplaced: dict[str, list[PlacedNotion]] = defaultdict(list)
    for item, lesson in rows:
        mastery = masteries.get(item.id)
        level = notion_level(to_mastery(mastery), item.required_levels).level if mastery else 0
        notion = PlacedNotion(item.label, lesson.id, lesson.title, int(level))
        text = f"{lesson.title or ''} {item.label} {item.statement}"
        found = place(programme, lesson.subject, child.grade, text)
        if found is None:
            if lesson.subject in programme.subjects:
                unplaced[lesson.subject].append(notion)
        elif found.grade_match:
            placed[found.sub.id].append(notion)
        else:
            elsewhere[found.sub.id].append(notion)

    by_id = {s.id: s for subs in programme.subjects for s in programme.subs(subs)}
    order = [s.value for s in Subject]
    subjects = []
    for subject in sorted(programme.subjects, key=lambda s: order.index(s) if s in order else len(order)):
        domains = [
            DomainProgress(
                domain.title,
                [
                    CompetenceProgress(c.title, [SubProgress(s, placed.get(s.id, [])) for s in c.subs])
                    for c in domain.competences
                ],
            )
            for domain in programme.for_grade(subject, child.grade)
        ]
        if not domains:
            continue
        other = [
            SubProgress(by_id[i], notions) for i, notions in elsewhere.items() if by_id[i].subject == subject
        ]
        subjects.append(SubjectProgress(subject, domains, other, unplaced.get(subject, [])))
    return ProgrammeProgress(child.grade, programme.version, programme.source, subjects)
