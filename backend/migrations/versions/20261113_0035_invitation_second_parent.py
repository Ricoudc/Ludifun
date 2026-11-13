"""invitation d'un second parent (§5.92)

Un parent invite un autre parent dans sa famille avec un code (8 caractères, 7 jours, usage
unique ; seule l'empreinte est gardée). Le rôle « member » existait déjà dans `family_members`.
Table nouvelle, rien à reprendre. Retour arrière : la table disparaît ; les seconds parents
déjà entrés restent membres de la famille.

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-13 20:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035"
down_revision: str | Sequence[str] | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "family_invites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["family_id"],
            ["families.id"],
            name=op.f("fk_family_invites_family_id_families"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_family_invites")),
        sa.UniqueConstraint("code_hash", name=op.f("uq_family_invites_code_hash")),
    )
    op.create_index(op.f("ix_family_invites_family_id"), "family_invites", ["family_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_family_invites_family_id"), table_name="family_invites")
    op.drop_table("family_invites")
