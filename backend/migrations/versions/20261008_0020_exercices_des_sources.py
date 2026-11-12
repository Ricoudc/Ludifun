"""exercices tirés des sites de confiance (étape 29)

`ai_runs.stage` accepte `practice` : l'IA tire des questions d'extraits de sites éducatifs
autorisés, journalisée comme les autres appels. Les questions gardées vont dans le matériel de la
notion (JSON, champ `source` de chaque question) : rien d'autre à changer, rien à reprendre.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-08 10:30:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STAGES = "'ocr', 'analysis', 'material', 'evaluation', 'sources', 'illustration'"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_ai_runs_stage"), "ai_runs", type_="check")
    op.create_check_constraint(op.f("ck_ai_runs_stage"), "ai_runs", f"stage IN ({STAGES}, 'practice')")


def downgrade() -> None:
    op.execute("DELETE FROM ai_runs WHERE stage = 'practice'")
    op.drop_constraint(op.f("ck_ai_runs_stage"), "ai_runs", type_="check")
    op.create_check_constraint(op.f("ck_ai_runs_stage"), "ai_runs", f"stage IN ({STAGES})")
