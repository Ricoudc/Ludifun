"""questions signalées par l'enfant (🚩)

`question_reports` : une question signalée pendant une séance (« Ma réponse était juste »,
« Je ne comprends pas la question », « Il y a une erreur »), au plus une par question ; le
parent la voit et la marque comme vue (`seen_at`). Rien à reprendre : la fonction est nouvelle.

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-08 21:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | Sequence[str] | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "question_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_item_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "reason IN ('right_answer', 'unclear', 'wrong_question')",
            name=op.f("ck_question_reports_reason"),
        ),
        sa.ForeignKeyConstraint(
            ["session_item_id"],
            ["session_items.id"],
            name=op.f("fk_question_reports_session_item_id_session_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_reports")),
        sa.UniqueConstraint("session_item_id", name=op.f("uq_question_reports_session_item_id")),
    )


def downgrade() -> None:
    op.drop_table("question_reports")
