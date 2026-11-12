"""recherche de sources (étape 24, CDC §116-117)

`ai_runs.stage` accepte `sources` : l'IA lit des extraits trouvés par Ludifun sur des sites
autorisés et explique en les citant. Journalisé comme les autres appels (§136).

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-25 16:00:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_ai_runs_stage"), "ai_runs", type_="check")
    op.create_check_constraint(
        op.f("ck_ai_runs_stage"),
        "ai_runs",
        "stage IN ('ocr', 'analysis', 'material', 'evaluation', 'sources')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM ai_runs WHERE stage = 'sources'")
    op.drop_constraint(op.f("ck_ai_runs_stage"), "ai_runs", type_="check")
    op.create_check_constraint(
        op.f("ck_ai_runs_stage"), "ai_runs", "stage IN ('ocr', 'analysis', 'material', 'evaluation')"
    )
