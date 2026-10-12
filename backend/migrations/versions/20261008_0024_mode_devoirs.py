"""mode devoirs : l'enfant est guidé pas à pas sur son exercice (CDC §29, §127)

`homework` : l'énoncé lu (la photo n'est pas gardée), le plan proposé par l'IA et contrôlé par
le code, les étapes montrées et les tentatives. `ai_runs.stage` accepte `homework`. Rien à
reprendre : la fonction est nouvelle.

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-08 22:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024"
down_revision: str | Sequence[str] | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STAGES = "'ocr', 'analysis', 'material', 'evaluation', 'sources', 'illustration', 'practice'"


def upgrade() -> None:
    op.create_table(
        "homework",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("child_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=True),
        sa.Column("plan", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("steps_shown", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("attempts", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('preparing', 'ready', 'solved', 'guided', 'failed')", name=op.f("ck_homework_status")
        ),
        sa.CheckConstraint("source IN ('photo', 'text')", name=op.f("ck_homework_source")),
        sa.ForeignKeyConstraint(
            ["child_id"], ["children.id"], name=op.f("fk_homework_child_id_children"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_homework")),
    )
    op.create_index(op.f("ix_homework_child_id"), "homework", ["child_id"])
    op.drop_constraint(op.f("ck_ai_runs_stage"), "ai_runs", type_="check")
    op.create_check_constraint(op.f("ck_ai_runs_stage"), "ai_runs", f"stage IN ({STAGES}, 'homework')")


def downgrade() -> None:
    op.execute("DELETE FROM ai_runs WHERE stage = 'homework'")
    op.drop_constraint(op.f("ck_ai_runs_stage"), "ai_runs", type_="check")
    op.create_check_constraint(op.f("ck_ai_runs_stage"), "ai_runs", f"stage IN ({STAGES})")
    op.drop_index(op.f("ix_homework_child_id"), table_name="homework")
    op.drop_table("homework")
