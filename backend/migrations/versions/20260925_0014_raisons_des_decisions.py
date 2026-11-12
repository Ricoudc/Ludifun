"""raison des décisions et version du moteur (étape 23, CDC §126, §138)

`session_items.reason` : la règle qui a fait choisir l'activité et ses faits.
`sessions.engine_version` : version des règles du moteur (engine_rules.toml) ; null avant.
`sessions.decisions` : décisions prises pendant la séance (remédiation, pause, défis bonus).
`family_ai_settings.fallback` : repli sur les autres IA de la famille, si le parent le permet (§147).

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-25 06:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "session_items", sa.Column("reason", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.add_column("sessions", sa.Column("engine_version", sa.Text(), nullable=True))
    op.add_column(
        "sessions",
        sa.Column("decisions", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
    )

    op.add_column(
        "family_ai_settings",
        sa.Column("fallback", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("family_ai_settings", "fallback")
    op.drop_column("sessions", "decisions")
    op.drop_column("sessions", "engine_version")
    op.drop_column("session_items", "reason")
