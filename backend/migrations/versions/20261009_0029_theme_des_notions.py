"""notions : thème choisi par l'IA dans une liste fermée (spécification technique §5.47)

`knowledge_items.theme` (facultatif) : « heure », « conjugaison », « fractions »… Il déclenche les
jeux calculés par le code. Pas de contrainte en base : la liste est contrôlée par
`app.domain.knowledge.theme_fits` à l'analyse, et une valeur inconnue est ignorée au chargement
(elle peut donc grandir sans migration). Reprise : les notions déjà analysées restent sans thème
et gardent la détection par mots-clés.

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-09 16:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | Sequence[str] | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("knowledge_items", sa.Column("theme", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("knowledge_items", "theme")
