"""index pour l'historique des réponses par notion

La lecture de l'historique adaptatif filtre d'abord les preuves par notion.
La clé primaire actuelle commence par attempt_id ; cet index permet de retrouver
les tentatives d'une notion sans parcourir toutes les preuves.

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-11 07:00:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0033"
down_revision: str | Sequence[str] | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_attempt_evidence_knowledge_attempt",
        "attempt_evidence",
        ["knowledge_id", "attempt_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_attempt_evidence_knowledge_attempt", table_name="attempt_evidence")
