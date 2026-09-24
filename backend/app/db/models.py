"""Tables de la V1 (cahier des charges §12).

Toute modification ici doit s'accompagner d'une migration Alembic :
    uv run alembic revision --autogenerate -m "..."
Le test `test_models_match_migrations` échoue si les deux divergent.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ARRAY,
    REAL,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
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

LESSON_STATUSES = ("uploaded", "reading", "needs_review", "analyzing", "generating", "ready", "failed")
LESSON_SOURCES = ("photo", "text")
REVIEW_STATUSES = ("pending", "confirmed", "corrected", "unknown")
FAILURE_REASONS = ("unreadable", "not_a_lesson", "too_long", "ai_error")
PAGE_QUALITIES = ("good", "partial", "unreadable")
SESSION_KINDS = ("first", "review", "errors")
SESSION_STATUSES = ("active", "completed", "abandoned")
SESSION_BLOCKS = ("warmup", "core", "match", "speed", "replay", "remediation", "bonus")
ERROR_TYPES = (
    "knowledge",
    "calculation",
    "method",
    "reading",
    "confusion",
    "forgotten",
    "imprecision",
    "random",
    "statement",
)
SKILL_VERBS = ("recognize", "recall", "apply", "explain", "transfer")
AI_STAGES = ("ocr", "analysis", "material", "evaluation")
AI_RUN_STATUSES = ("ok", "invalid_output", "refused", "error")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _fk(target: str, ondelete: str = "CASCADE", nullable: bool = False) -> Mapped[Any]:
    return mapped_column(Uuid, ForeignKey(target, ondelete=ondelete), nullable=nullable)


# --------------------------------------------------------------------------- #
# Comptes : parent → famille → enfants → appareils (cahier des charges §12)
# --------------------------------------------------------------------------- #

FAMILY_ROLES = ("owner", "member")


class Parent(Base):
    __tablename__ = "parents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)  # en minuscules
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)  # argon2id
    privacy_accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Family(Base):
    """Un parent en V1 ; un second parent pourra rejoindre la famille en V5."""

    __tablename__ = "families"

    id: Mapped[uuid.UUID] = _uuid_pk()
    created_at: Mapped[datetime] = _created_at()


class FamilyMember(Base):
    __tablename__ = "family_members"

    family_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("families.id", ondelete="CASCADE"), primary_key=True
    )
    parent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("parents.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (CheckConstraint(_in("role", FAMILY_ROLES), name="role"), Index(None, "parent_id"))


class Child(Base):
    __tablename__ = "children"

    id: Mapped[uuid.UUID] = _uuid_pk()
    family_id: Mapped[uuid.UUID] = _fk("families.id")
    display_name: Mapped[str] = mapped_column(Text, nullable=False)  # prénom ou pseudo
    grade: Mapped[str] = mapped_column(Text, nullable=False)
    avatar: Mapped[str | None] = mapped_column(Text)
    parental_consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = _created_at()
    # Objectifs du parent (étape 16) : minutes de révision par jour, matière à privilégier.
    daily_minutes: Mapped[int | None] = mapped_column(SmallInteger)
    priority_subject: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index(None, "family_id"),
        CheckConstraint("daily_minutes IN (5, 10, 15, 20, 30)", name="daily_minutes"),
    )


class Exam(Base):
    """Contrôle à venir, saisi par le parent : le plan de révision est recalculé chaque jour."""

    __tablename__ = "exams"

    id: Mapped[uuid.UUID] = _uuid_pk()
    child_id: Mapped[uuid.UUID] = _fk("children.id")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    exam_date: Mapped[date] = mapped_column(Date, nullable=False)
    lesson_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid), nullable=False)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (Index(None, "child_id", "exam_date"),)


class Device(Base):
    """Appareil de l'enfant, lié par code ou QR code."""

    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = _uuid_pk()
    child_id: Mapped[uuid.UUID] = _fk("children.id")
    # SHA-256 du jeton d'appareil : le jeton en clair n'est jamais stocké.
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index(None, "child_id"),)


class LinkCode(Base):
    """Code à 6 chiffres et jeton de QR code, valables 10 minutes, à usage unique."""

    __tablename__ = "link_codes"

    id: Mapped[uuid.UUID] = _uuid_pk()
    child_id: Mapped[uuid.UUID] = _fk("children.id")
    code_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    qr_token_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index(None, "code_hash"), Index(None, "child_id"))


class RefreshToken(Base):
    """Jeton de renouvellement du parent ; rotation à chaque usage (§16.1)."""

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = _uuid_pk()
    parent_id: Mapped[uuid.UUID] = _fk("parents.id")
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by: Mapped[uuid.UUID | None] = _fk("refresh_tokens.id", ondelete="SET NULL", nullable=True)

    __table_args__ = (Index(None, "parent_id"),)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = _uuid_pk()
    parent_id: Mapped[uuid.UUID] = _fk("parents.id")
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index(None, "parent_id"),)


class Lesson(Base):
    __tablename__ = "lessons"

    id: Mapped[uuid.UUID] = _uuid_pk()
    child_id: Mapped[uuid.UUID] = _fk("children.id")
    status: Mapped[str] = mapped_column(Text, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text)
    grade: Mapped[str | None] = mapped_column(Text)
    grade_confidence: Mapped[float | None] = mapped_column(REAL)
    title: Mapped[str | None] = mapped_column(Text)
    objective: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="photo")  # photo ou texte collé
    analysis: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    prompt_versions: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(_in("status", LESSON_STATUSES), name="status"),
        CheckConstraint(_in("failure_reason", FAILURE_REASONS), name="failure_reason"),
        CheckConstraint(_in("source", LESSON_SOURCES), name="source"),
        CheckConstraint("page_count BETWEEN 1 AND 6", name="page_count"),
        Index("ix_lessons_child_recent", "child_id", text("created_at DESC")),
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


class LessonReviewItem(Base):
    """Passage mal lu sur la photo, à vérifier par l'enfant avant l'analyse (étape 15)."""

    __tablename__ = "lesson_review_items"

    id: Mapped[uuid.UUID] = _uuid_pk()
    lesson_id: Mapped[uuid.UUID] = _fk("lessons.id")
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    page_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    read_text: Mapped[str] = mapped_column(Text, nullable=False)  # ce que l'OCR croit avoir lu
    context: Mapped[str] = mapped_column(Text, nullable=False)  # les mots autour, pour le retrouver
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    answer: Mapped[str | None] = mapped_column(Text)  # la correction de l'enfant

    __table_args__ = (
        UniqueConstraint("lesson_id", "position"),
        CheckConstraint(_in("status", REVIEW_STATUSES), name="status"),
    )


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
    # Niveaux de compréhension à valider pour « maîtrisée » (1 reconnaître … 5 transférer),
    # fixés à l'analyse d'après le matériel disponible (spécification technique §5.1).
    required_levels: Mapped[list[int]] = mapped_column(
        ARRAY(SmallInteger), nullable=False, server_default="{1}"
    )

    __table_args__ = (
        UniqueConstraint("lesson_id", "key"),
        CheckConstraint("importance BETWEEN 1 AND 5", name="importance"),
    )


class Skill(Base):
    """Compétence visée par une leçon (« Comparer deux fractions »), reliée à ses notions."""

    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = _uuid_pk()
    lesson_id: Mapped[uuid.UUID] = _fk("lessons.id")
    key: Mapped[str] = mapped_column(Text, nullable=False)  # "s1"
    label: Mapped[str] = mapped_column(Text, nullable=False)
    verb: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    source_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint("lesson_id", "key"),
        CheckConstraint(_in("verb", SKILL_VERBS), name="verb"),
        CheckConstraint("importance BETWEEN 1 AND 5", name="importance"),
    )


class SkillKnowledge(Base):
    __tablename__ = "skill_knowledge"

    skill_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )
    knowledge_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("knowledge_items.id", ondelete="CASCADE"), primary_key=True
    )

    __table_args__ = (Index(None, "knowledge_id"),)


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
    child_id: Mapped[uuid.UUID] = _fk("children.id")
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
    # Étape 17 : réponses données quand la dernière pause a été proposée ; défis bonus ajoutés.
    hint_at_answer: Mapped[int | None] = mapped_column(SmallInteger)
    extended: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    __table_args__ = (
        CheckConstraint(_in("kind", SESSION_KINDS), name="kind"),
        CheckConstraint(_in("status", SESSION_STATUSES), name="status"),
        Index("ix_sessions_child_recent", "child_id", text("started_at DESC")),
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
    # 1 reconnaître, 2 se rappeler, 3 appliquer, 4 expliquer, 5 transférer.
    cognitive_level: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    # Aide la plus forte demandée (« Je n'ai pas compris ») avant la réponse : 0 à 5.
    help_level: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    intro: Mapped[str | None] = mapped_column(Text)  # « Rappel » affiché avant l'activité (remédiation)
    knowledge_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)  # envoyé au téléphone
    solution: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)  # jamais avant la réponse

    __table_args__ = (
        UniqueConstraint("session_id", "position"),
        CheckConstraint(_in("block", SESSION_BLOCKS), name="block"),
        CheckConstraint("difficulty BETWEEN 1 AND 3", name="difficulty"),
        CheckConstraint("cognitive_level BETWEEN 1 AND 5", name="cognitive_level"),
        CheckConstraint("help_level BETWEEN 0 AND 5", name="help_level"),
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
    error_type: Mapped[str | None] = mapped_column(Text)  # notion ratée : pourquoi (§5.5)

    __table_args__ = (
        CheckConstraint("result BETWEEN 0 AND 1", name="result"),
        CheckConstraint("weight > 0 AND weight <= 1", name="weight"),
        CheckConstraint(_in("error_type", ERROR_TYPES), name="error_type"),
    )


class KnowledgeMastery(Base):
    __tablename__ = "knowledge_mastery"

    child_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("children.id", ondelete="CASCADE"), primary_key=True
    )
    knowledge_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("knowledge_items.id", ondelete="CASCADE"), primary_key=True
    )
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    box: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    next_review_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_practiced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sessions_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    levels: Mapped[list[int]] = mapped_column(  # niveaux de compréhension validés
        ARRAY(SmallInteger), nullable=False, server_default="{}"
    )

    __table_args__ = (
        CheckConstraint("score BETWEEN 0 AND 100", name="score"),
        CheckConstraint("box BETWEEN 1 AND 5", name="box"),
        Index("ix_knowledge_mastery_due", "child_id", "next_review_at"),
    )


class Feedback(Base):
    """Avis d'un parent ou d'un enfant (tests en famille, étape 18). Supprimé avec son auteur."""

    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = _uuid_pk()
    parent_id: Mapped[uuid.UUID | None] = _fk("parents.id", nullable=True)
    child_id: Mapped[uuid.UUID | None] = _fk("children.id", nullable=True)
    author: Mapped[str] = mapped_column(Text, nullable=False)  # parent ou child
    rating: Mapped[int | None] = mapped_column(SmallInteger)  # 1 à 5
    message: Mapped[str | None] = mapped_column(Text)
    screen: Mapped[str | None] = mapped_column(Text)  # d'où vient l'avis (bilan, réglages…)
    session_id: Mapped[uuid.UUID | None] = _fk("sessions.id", ondelete="SET NULL", nullable=True)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        CheckConstraint(_in("author", ("parent", "child")), name="author"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating"),
        CheckConstraint("rating IS NOT NULL OR message IS NOT NULL", name="content"),
        CheckConstraint("(author = 'parent') = (parent_id IS NOT NULL)", name="parent_author"),
        CheckConstraint("author = 'parent' OR child_id IS NOT NULL", name="child_author"),
        Index(None, "created_at"),
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
