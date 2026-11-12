"""« Enseigne-moi » : l'enfant explique une notion à Ludi, l'élève joué par l'IA (CDC §83)

`teach_sessions` : la notion expliquée, les points clés attendus, les tours (question de Ludi,
explication de l'enfant, points reconnus), le bilan et la raison de la décision du moteur.
`ai_runs.stage` accepte `teach`. Rien à reprendre : la fonction est nouvelle.

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-09 06:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025"
down_revision: str | Sequence[str] | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STAGES = "'ocr', 'analysis', 'material', 'evaluation', 'sources', 'illustration', 'practice', 'homework'"


def upgrade() -> None:
    op.create_table(
        "teach_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("child_id", sa.Uuid(), nullable=False),
        sa.Column("lesson_id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("key_points", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("turns", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("covered", sa.SmallInteger(), nullable=True),
        sa.Column("validated", sa.Boolean(), nullable=True),
        sa.Column("decision", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("engine_version", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('open', 'finished')", name=op.f("ck_teach_sessions_status")),
        sa.ForeignKeyConstraint(
            ["child_id"],
            ["children.id"],
            name=op.f("fk_teach_sessions_child_id_children"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["lessons.id"],
            name=op.f("fk_teach_sessions_lesson_id_lessons"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_id"],
            ["knowledge_items.id"],
            name=op.f("fk_teach_sessions_knowledge_id_knowledge_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teach_sessions")),
    )
    op.create_index(op.f("ix_teach_sessions_child_id"), "teach_sessions", ["child_id"])
    op.create_index(op.f("ix_teach_sessions_lesson_id"), "teach_sessions", ["lesson_id"])
    op.drop_constraint(op.f("ck_ai_runs_stage"), "ai_runs", type_="check")
    op.create_check_constraint(op.f("ck_ai_runs_stage"), "ai_runs", f"stage IN ({STAGES}, 'teach')")


def downgrade() -> None:
    op.execute("DELETE FROM ai_runs WHERE stage = 'teach'")
    op.drop_constraint(op.f("ck_ai_runs_stage"), "ai_runs", type_="check")
    op.create_check_constraint(op.f("ck_ai_runs_stage"), "ai_runs", f"stage IN ({STAGES})")
    op.drop_index(op.f("ix_teach_sessions_lesson_id"), table_name="teach_sessions")
    op.drop_index(op.f("ix_teach_sessions_child_id"), table_name="teach_sessions")
    op.drop_table("teach_sessions")
