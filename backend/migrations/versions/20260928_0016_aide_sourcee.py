"""aide sourcée et réglage du parent (étape 24b, CDC §116-117)

`families.web_sources` : le parent autorise la recherche sur des sites éducatifs (désactivée).
`knowledge_items.external_help` : explication tirée de ces sources, avec citations vérifiées,
proposée par « Je n'ai pas compris » quand la leçon ne donne pas d'exemple.

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-28 09:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "families", sa.Column("web_sources", sa.Boolean(), server_default=sa.text("false"), nullable=False)
    )
    op.add_column(
        "knowledge_items",
        sa.Column("external_help", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("knowledge_items", "external_help")
    op.drop_column("families", "web_sources")
