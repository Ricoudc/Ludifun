"""ressources : les sites de confiance choisis par la famille (§5.60)

`lesson_resources.provider` accepte Logiciel Éducatif, Bout de Gomme, Mathador, Khan Academy,
La Main à la Pâte, la Cité des sciences, Vie-publique, Géoconfluences, Annabac et les partenaires
d'Éduthèque (Louvre, BnF, INA, CNES, Météo-France, Versailles). Rien à reprendre.

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-12 09:00:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0030"
down_revision: str | Sequence[str] | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEFORE = ("mathalea", "vikidia", "lumni", "fondamentaux", "maitrelucas", "calculatice", "sesamath")
ADDED = (
    "logicieleducatif",
    "boutdegomme",
    "mathador",
    "khanacademy",
    "lamap",
    "citesciences",
    "viepublique",
    "geoconfluences",
    "annabac",
    "louvre",
    "bnf",
    "ina",
    "cnes",
    "meteofrance",
    "versailles",
)


def _sql(names: Sequence[str]) -> str:
    return ", ".join(f"'{n}'" for n in names)


def _constraint(providers: Sequence[str]) -> None:
    op.drop_constraint(op.f("ck_lesson_resources_provider"), "lesson_resources", type_="check")
    op.create_check_constraint(
        op.f("ck_lesson_resources_provider"), "lesson_resources", f"provider IN ({_sql(providers)})"
    )


def upgrade() -> None:
    _constraint((*BEFORE, *ADDED))


def downgrade() -> None:
    op.execute(f"DELETE FROM lesson_resources WHERE provider IN ({_sql(ADDED)})")
    _constraint(BEFORE)
