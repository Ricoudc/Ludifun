"""notes du parent pendant l'essai de la leçon (§5.90)

Le parent qui essaie la leçon note « Il y a une erreur dans cette question » : la note est
gardée (`trial_notes`) pour qu'il la corrige ensuite dans « Questions de la leçon ». Table
nouvelle, rien à reprendre. Retour arrière : la table disparaît avec ses notes.

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-13 18:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: str | Sequence[str] | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trial_notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lesson_id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_id", sa.Uuid(), nullable=False),
        sa.Column("activity_type", sa.Text(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["lesson_id"], ["lessons.id"], name=op.f("fk_trial_notes_lesson_id_lessons"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_id"],
            ["knowledge_items.id"],
            name=op.f("fk_trial_notes_knowledge_id_knowledge_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trial_notes")),
    )
    op.create_index(op.f("ix_trial_notes_lesson_id"), "trial_notes", ["lesson_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_trial_notes_lesson_id"), table_name="trial_notes")
    op.drop_table("trial_notes")
