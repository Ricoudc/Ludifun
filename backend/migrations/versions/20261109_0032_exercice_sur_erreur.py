"""exercice neuf sur une erreur qui revient (§5.74)

`ai_runs.stage` accepte `targeted` : l'IA propose des questions qui visent une erreur
récurrente, enregistrées dans le matériel de la notion (JSONB, champ `target_error`, sans
changement de table). Rien à reprendre.

Retour arrière : les traces `targeted` du suivi sont effacées (journal technique), puis la
contrainte revient à la liste d'avant ; les questions déjà ajoutées restent dans le matériel.

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-09 09:30:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0032"
down_revision: str | Sequence[str] | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STAGES = (
    "'ocr', 'analysis', 'material', 'evaluation', 'sources', 'illustration', 'practice', 'homework', 'teach'"
)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_ai_runs_stage"), "ai_runs", type_="check")
    op.create_check_constraint(op.f("ck_ai_runs_stage"), "ai_runs", f"stage IN ({STAGES}, 'targeted')")


def downgrade() -> None:
    op.execute("DELETE FROM ai_runs WHERE stage = 'targeted'")
    op.drop_constraint(op.f("ck_ai_runs_stage"), "ai_runs", type_="check")
    op.create_check_constraint(op.f("ck_ai_runs_stage"), "ai_runs", f"stage IN ({STAGES})")
