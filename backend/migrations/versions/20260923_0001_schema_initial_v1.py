"""schema initial v1

Revision ID: 0001
Revises:
Create Date: 2026-09-23 13:23:43.806232

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "devices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_devices")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_devices_token_hash")),
    )
    op.create_table(
        "learners",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.id"], name=op.f("fk_learners_device_id_devices"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_learners")),
    )
    op.create_index(op.f("ix_learners_device_id"), "learners", ["device_id"], unique=False)
    op.create_table(
        "lessons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("learner_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("grade", sa.Text(), nullable=True),
        sa.Column("grade_confidence", sa.REAL(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("objective", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("page_count", sa.SmallInteger(), nullable=False),
        sa.Column("analysis", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("prompt_versions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "failure_reason IN ('unreadable', 'not_a_lesson', 'too_long', 'ai_error')",
            name=op.f("ck_lessons_failure_reason"),
        ),
        sa.CheckConstraint(
            "status IN ('uploaded', 'reading', 'analyzing', 'generating', 'ready', 'failed')",
            name=op.f("ck_lessons_status"),
        ),
        sa.CheckConstraint("page_count BETWEEN 1 AND 6", name=op.f("ck_lessons_page_count")),
        sa.ForeignKeyConstraint(
            ["learner_id"], ["learners.id"], name=op.f("fk_lessons_learner_id_learners"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lessons")),
    )
    op.create_index(
        "ix_lessons_learner_recent",
        "lessons",
        ["learner_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_table(
        "ai_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lesson_id", sa.Uuid(), nullable=True),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("stage IN ('ocr', 'analysis', 'material')", name=op.f("ck_ai_runs_stage")),
        sa.CheckConstraint(
            "status IN ('ok', 'invalid_output', 'refused', 'error')", name=op.f("ck_ai_runs_status")
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"], ["lessons.id"], name=op.f("fk_ai_runs_lesson_id_lessons"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_runs")),
    )
    op.create_index(op.f("ix_ai_runs_lesson_id"), "ai_runs", ["lesson_id"], unique=False)
    op.create_table(
        "knowledge_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lesson_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("importance", sa.SmallInteger(), nullable=False),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("relations", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("source_excerpt", sa.Text(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint("importance BETWEEN 1 AND 5", name=op.f("ck_knowledge_items_importance")),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["lessons.id"],
            name=op.f("fk_knowledge_items_lesson_id_lessons"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_items")),
        sa.UniqueConstraint("lesson_id", "key", name=op.f("uq_knowledge_items_lesson_id_key")),
    )
    op.create_table(
        "lesson_pages",
        sa.Column("lesson_id", sa.Uuid(), nullable=False),
        sa.Column("page_index", sa.SmallInteger(), nullable=False),
        sa.Column("ocr_text", sa.Text(), nullable=False),
        sa.Column("quality", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "quality IN ('good', 'partial', 'unreadable')", name=op.f("ck_lesson_pages_quality")
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"], ["lessons.id"], name=op.f("fk_lesson_pages_lesson_id_lessons"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("lesson_id", "page_index", name=op.f("pk_lesson_pages")),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("learner_id", sa.Uuid(), nullable=False),
        sa.Column("lesson_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("parent_session_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("estimated_duration_s", sa.Integer(), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("score_on_10", sa.Numeric(precision=3, scale=1), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('first', 'review', 'errors')", name=op.f("ck_sessions_kind")),
        sa.CheckConstraint("status IN ('active', 'completed', 'abandoned')", name=op.f("ck_sessions_status")),
        sa.ForeignKeyConstraint(
            ["learner_id"], ["learners.id"], name=op.f("fk_sessions_learner_id_learners"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"], ["lessons.id"], name=op.f("fk_sessions_lesson_id_lessons"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["parent_session_id"],
            ["sessions.id"],
            name=op.f("fk_sessions_parent_session_id_sessions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
    )
    op.create_index(
        "ix_sessions_learner_recent",
        "sessions",
        ["learner_id", sa.literal_column("started_at DESC")],
        unique=False,
    )
    op.create_index(op.f("ix_sessions_lesson_id"), "sessions", ["lesson_id"], unique=False)
    op.create_table(
        "knowledge_mastery",
        sa.Column("learner_id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column("box", sa.SmallInteger(), nullable=False),
        sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_practiced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sessions_count", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint("box BETWEEN 1 AND 5", name=op.f("ck_knowledge_mastery_box")),
        sa.CheckConstraint("score BETWEEN 0 AND 100", name=op.f("ck_knowledge_mastery_score")),
        sa.ForeignKeyConstraint(
            ["knowledge_id"],
            ["knowledge_items.id"],
            name=op.f("fk_knowledge_mastery_knowledge_id_knowledge_items"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["learner_id"],
            ["learners.id"],
            name=op.f("fk_knowledge_mastery_learner_id_learners"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("learner_id", "knowledge_id", name=op.f("pk_knowledge_mastery")),
    )
    op.create_index(
        "ix_knowledge_mastery_due", "knowledge_mastery", ["learner_id", "next_review_at"], unique=False
    )
    op.create_table(
        "knowledge_material",
        sa.Column("knowledge_id", sa.Uuid(), nullable=False),
        sa.Column("material", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rejected", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["knowledge_id"],
            ["knowledge_items.id"],
            name=op.f("fk_knowledge_material_knowledge_id_knowledge_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("knowledge_id", name=op.f("pk_knowledge_material")),
    )
    op.create_table(
        "session_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("block", sa.Text(), nullable=False),
        sa.Column("activity_type", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.SmallInteger(), nullable=False),
        sa.Column("knowledge_ids", sa.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("solution", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "block IN ('warmup', 'core', 'match', 'speed', 'replay')", name=op.f("ck_session_items_block")
        ),
        sa.CheckConstraint("difficulty BETWEEN 1 AND 3", name=op.f("ck_session_items_difficulty")),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name=op.f("fk_session_items_session_id_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_session_items")),
        sa.UniqueConstraint("session_id", "position", name=op.f("uq_session_items_session_id_position")),
    )
    op.create_table(
        "attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_item_id", sa.Uuid(), nullable=False),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("score", sa.Numeric(precision=3, scale=2), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("score BETWEEN 0 AND 1", name=op.f("ck_attempts_score")),
        sa.ForeignKeyConstraint(
            ["session_item_id"],
            ["session_items.id"],
            name=op.f("fk_attempts_session_item_id_session_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attempts")),
        sa.UniqueConstraint("session_item_id", name=op.f("uq_attempts_session_item_id")),
    )
    op.create_table(
        "attempt_evidence",
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_id", sa.Uuid(), nullable=False),
        sa.Column("result", sa.Numeric(precision=3, scale=2), nullable=False),
        sa.Column("weight", sa.Numeric(precision=3, scale=2), nullable=False),
        sa.CheckConstraint("result BETWEEN 0 AND 1", name=op.f("ck_attempt_evidence_result")),
        sa.CheckConstraint("weight > 0 AND weight <= 1", name=op.f("ck_attempt_evidence_weight")),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["attempts.id"],
            name=op.f("fk_attempt_evidence_attempt_id_attempts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_id"],
            ["knowledge_items.id"],
            name=op.f("fk_attempt_evidence_knowledge_id_knowledge_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("attempt_id", "knowledge_id", name=op.f("pk_attempt_evidence")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("attempt_evidence")
    op.drop_table("attempts")
    op.drop_table("session_items")
    op.drop_table("knowledge_material")
    op.drop_index("ix_knowledge_mastery_due", table_name="knowledge_mastery")
    op.drop_table("knowledge_mastery")
    op.drop_index(op.f("ix_sessions_lesson_id"), table_name="sessions")
    op.drop_index("ix_sessions_learner_recent", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("lesson_pages")
    op.drop_table("knowledge_items")
    op.drop_index(op.f("ix_ai_runs_lesson_id"), table_name="ai_runs")
    op.drop_table("ai_runs")
    op.drop_index("ix_lessons_learner_recent", table_name="lessons")
    op.drop_table("lessons")
    op.drop_index(op.f("ix_learners_device_id"), table_name="learners")
    op.drop_table("learners")
    op.drop_table("devices")
