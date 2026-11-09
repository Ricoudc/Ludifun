"""relecture par le parent : la leçon attend sa validation avant l'enfant (§5.69)

- `families.review_lessons` : « Je relis chaque leçon avant mon enfant », coché par défaut ;
- `lessons.parent_approved_at` : quand le parent a validé la leçon. Les leçons existantes sont
  reprises comme validées (à leur date de création) : l'enfant les garde ;
- `knowledge_items.removed_at` : notion retirée par le parent (inventée, fausse), plus jamais
  proposée à l'enfant, remise d'un geste.

Retour arrière : les colonnes disparaissent ; une notion retirée redevient proposée.

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-07 15:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | Sequence[str] | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "families", sa.Column("review_lessons", sa.Boolean(), nullable=False, server_default=sa.true())
    )
    op.add_column("lessons", sa.Column("parent_approved_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE lessons SET parent_approved_at = created_at")
    op.add_column("knowledge_items", sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("knowledge_items", "removed_at")
    op.drop_column("lessons", "parent_approved_at")
    op.drop_column("families", "review_lessons")
