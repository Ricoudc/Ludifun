"""bilan de la semaine par e-mail (§5.93)

`parents.weekly_email` (désactivé par défaut : le parent choisit) et `weekly_email_sent_at`
(dernier envoi, pour ne jamais envoyer deux fois la même semaine). Les comptes existants ne
reçoivent rien tant que le parent ne l'a pas demandé. Retour arrière : les deux colonnes
disparaissent.

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-13 21:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036"
down_revision: str | Sequence[str] | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("parents", sa.Column("weekly_email", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("parents", sa.Column("weekly_email_sent_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("parents", "weekly_email_sent_at")
    op.drop_column("parents", "weekly_email")
