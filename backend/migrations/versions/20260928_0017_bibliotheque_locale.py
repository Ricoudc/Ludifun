"""bibliothèque sur le PC (étape 24d)

`library_pages` : pages de sites éducatifs autorisés déjà lues (Vikidia, Lumni, Éduscol…), pour
chercher des sources sans Internet (recherche plein texte en français de PostgreSQL). Contenu
public seulement.

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-28 11:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "library_pages",
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("site", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("url", name=op.f("pk_library_pages")),
    )
    op.create_index(op.f("ix_library_pages_site"), "library_pages", ["site"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_library_pages_site"), table_name="library_pages")
    op.drop_table("library_pages")
