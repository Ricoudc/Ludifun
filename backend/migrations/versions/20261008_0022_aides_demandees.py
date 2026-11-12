"""aides demandées (« Je n'ai pas compris ») avec leur heure

`help_requests` : chaque appui sur l'aide, avec l'heure, le niveau atteint et l'aide montrée ;
le parent voit quand l'enfant a demandé de l'aide. Rien à reprendre : les aides plus anciennes
n'ont pas d'heure enregistrée (leur niveau reste dans `session_items.help_level`, visible dans le
détail des séances).

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-08 19:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | Sequence[str] | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "help_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_item_id", sa.Uuid(), nullable=False),
        sa.Column("level", sa.SmallInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column(
            "requested_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("level BETWEEN 1 AND 5", name=op.f("ck_help_requests_level")),
        sa.CheckConstraint(
            "kind IN ('hint', 'reminder', 'example', 'steps', 'answer', 'sourced')",
            name=op.f("ck_help_requests_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["session_item_id"],
            ["session_items.id"],
            name=op.f("fk_help_requests_session_item_id_session_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_help_requests")),
    )
    op.create_index(op.f("ix_help_requests_session_item_id"), "help_requests", ["session_item_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_help_requests_session_item_id"), table_name="help_requests")
    op.drop_table("help_requests")
