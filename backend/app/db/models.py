"""Tables de la V1 (cahier des charges §12).

Toute modification ici doit s'accompagner d'une migration Alembic :
    uv run alembic revision --autogenerate -m "..."
Le test `test_models_match_migrations` échoue si les deux divergent.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ARRAY,
    REAL,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

LESSON_STATUSES = ("uploaded", "reading", "analyzing", "generating", "ready", "failed")
FAILURE_REASONS = ("unreadable", "not_a_lesson", "too_long", "ai_error")
PAGE_QUALITIES = ("good", "partial", "unreadable")
SESSION_KINDS = ("first", "review", "errors")
SESSION_STATUSES = ("active", "completed", "abandoned")
SESSION_BLOCKS = ("warmup", "core", "match", "speed", "replay")
AI_STAGES = ("ocr", "analysis", "material")
AI_RUN_STATUSES = ("ok", "invalid_output", "refused", "error")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _fk(target: str, ondelete: str = "CASCADE", nullable: bool = False) -> Mapped[Any]:
    return mapped_column(Uuid, ForeignKey(target, ondelete=ondelete), nullable=nullable)


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = _uuid_pk()
    # SHA-256 du jeton d'appareil : le jeton en clair n'est jamais stocké.
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    created_at: Mapped[datetime] = _created_at()
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Learner(Base):
    """V1 : un apprenant anonyme par appareil. V3 : plusieurs enfants par famille."""

    __tablename__ = "learners"

    id: Mapped[uuid.UUID] = _uuid_pk()
    device_id: Mapped[uuid.UUID] = _fk("devices.id")
    display_name: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (Index(None, "device_id"),)


class Lesson(Base):
    __tablename__ = "lessons"

    id: Mapped[uuid.UUID] = _uuid_pk()
    learner_id: Mapped[uuid.UUID] = _fk("learners.id")
    status: Mapped[str] = mapped_column(Text, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text)
    grade: Mapped[str | None] = mapped_column(Text)
    grade_confidence: Mapped[float | None] = mapped_column(REAL)
    title: Mapped[str | None] = mapped_column(Text)
    objective: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    analysis: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    prompt_versions: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(_in("status", LESSON_STATUSES), name="status"),
        CheckConstraint(_in("failure_reason", FAILURE_REASONS), name="failure_reason"),
        CheckConstraint("page_count BETWEEN 1 AND 6", name="page_count"),
        Index("ix_lessons_learner_recent", "learner_id", text("created_at DESC")),
    )


class LessonPage(Base):
    """Texte OCR d'une page. L'image elle-même n'est jamais stockée."""

    __tablename__ = "lesson_pages"

    lesson_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("lessons.id", ondelete="CASCADE"), primary_key=True
    )
    page_index: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    ocr_text: Mapped[str] = mapped_column(Text, nullable=False)
    quality: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (CheckConstraint(_in("quality", PAGE_QUALITIES), name="quality"),)


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"

    id: Mapped[uuid.UUID] = _uuid_pk()
    lesson_id: Mapped[uuid.UUID] = _fk("lessons.id")
    key: Mapped[str] = mapped_column(Text, nullable=False)  # "k1"
    type: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    relations: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    source_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint("lesson_id", "key"),
        CheckConstraint("importance BETWEEN 1 AND 5", name="importance"),
    )


class KnowledgeMaterial(Base):
    __tablename__ = "knowledge_material"

    knowledge_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("knowledge_items.id", ondelete="CASCADE"), primary_key=True
    )
    material: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    rejected: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)


class RevisionSession(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    learner_id: Mapped[uuid.UUID] = _fk("learners.id")
    lesson_id: Mapped[uuid.UUID] = _fk("lessons.id")
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    parent_session_id: Mapped[uuid.UUID | None] = _fk("sessions.id", ondelete="SET NULL", nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_duration_s: Mapped[int] = mapped_column(Integer, nullable=False)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    score_on_10: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    started_at: Mapped[datetime] = _created_at()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(_in("kind", SESSION_KINDS), name="kind"),
        CheckConstraint(_in("status", SESSION_STATUSES), name="status"),
        Index("ix_sessions_learner_recent", "learner_id", text("started_at DESC")),
        Index(None, "lesson_id"),
    )


class SessionItem(Base):
    __tablename__ = "session_items"

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = _fk("sessions.id")
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    block: Mapped[str] = mapped_column(Text, nullable=False)
    activity_type: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    knowledge_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)  # envoyé au téléphone
    solution: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)  # jamais avant la réponse

    __table_args__ = (
        UniqueConstraint("session_id", "position"),
        CheckConstraint(_in("block", SESSION_BLOCKS), name="block"),
        CheckConstraint("difficulty BETWEEN 1 AND 3", name="difficulty"),
    )


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("session_items.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (CheckConstraint("score BETWEEN 0 AND 1", name="score"),)


class AttemptEvidence(Base):
    """Une ligne par notion couverte par une tentative (§9.3)."""

    __tablename__ = "attempt_evidence"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("attempts.id", ondelete="CASCADE"), primary_key=True
    )
    knowledge_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("knowledge_items.id", ondelete="CASCADE"), primary_key=True
    )
    result: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False)
    weight: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False)

    __table_args__ = (
        CheckConstraint("result BETWEEN 0 AND 1", name="result"),
        CheckConstraint("weight > 0 AND weight <= 1", name="weight"),
    )


class KnowledgeMastery(Base):
    __tablename__ = "knowledge_mastery"

    learner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("learners.id", ondelete="CASCADE"), primary_key=True
    )
    knowledge_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("knowledge_items.id", ondelete="CASCADE"), primary_key=True
    )
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    box: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    next_review_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_practiced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sessions_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    __table_args__ = (
        CheckConstraint("score BETWEEN 0 AND 100", name="score"),
        CheckConstraint("box BETWEEN 1 AND 5", name="box"),
        Index("ix_knowledge_mastery_due", "learner_id", "next_review_at"),
    )


class AiRun(Base):
    """Coût, latence et qualité de chaque appel IA. Aucun contenu de leçon ici."""

    __tablename__ = "ai_runs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    lesson_id: Mapped[uuid.UUID | None] = _fk("lessons.id", ondelete="SET NULL", nullable=True)
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    warnings: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        CheckConstraint(_in("stage", AI_STAGES), name="stage"),
        CheckConstraint(_in("status", AI_RUN_STATUSES), name="status"),
        Index(None, "lesson_id"),
    )
