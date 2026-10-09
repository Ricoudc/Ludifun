"""confiance de chaque notion extraite (CDC §115)

`knowledge_items.confidence` (0 à 1, calculée par le code à l'analyse), `doubts` (ce qui fait
douter, pour le parent) et `confirmed_at` (le parent a confirmé la notion). Reprise : les notions
déjà analysées n'ont pas de confiance (NULL), elles restent utilisées comme avant.

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-09 09:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026"
down_revision: str | Sequence[str] | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("knowledge_items", sa.Column("confidence", sa.REAL(), nullable=True))
    op.add_column(
        "knowledge_items",
        sa.Column("doubts", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
    )
    op.add_column("knowledge_items", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        op.f("ck_knowledge_items_confidence"), "knowledge_items", "confidence BETWEEN 0 AND 1"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_knowledge_items_confidence"), "knowledge_items", type_="check")
    op.drop_column("knowledge_items", "confirmed_at")
    op.drop_column("knowledge_items", "doubts")
    op.drop_column("knowledge_items", "confidence")
