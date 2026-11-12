"""ressources : Calcul@TICE (jeux de calcul mental) et Sésamath (manuels libres)

`lesson_resources.provider` accepte `calculatice` et `sesamath` ; `kind` accepte `game` (un jeu
en ligne que Ludifun ne note pas). Rien à reprendre.

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-09 14:00:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0028"
down_revision: str | Sequence[str] | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROVIDERS = "'mathalea', 'vikidia', 'lumni', 'fondamentaux', 'maitrelucas'"
KINDS = "'exercise', 'quiz', 'video', 'article', 'lesson'"


def _constraints(providers: str, kinds: str) -> None:
    op.drop_constraint(op.f("ck_lesson_resources_provider"), "lesson_resources", type_="check")
    op.create_check_constraint(
        op.f("ck_lesson_resources_provider"), "lesson_resources", f"provider IN ({providers})"
    )
    op.drop_constraint(op.f("ck_lesson_resources_kind"), "lesson_resources", type_="check")
    op.create_check_constraint(op.f("ck_lesson_resources_kind"), "lesson_resources", f"kind IN ({kinds})")


def upgrade() -> None:
    _constraints(f"{PROVIDERS}, 'calculatice', 'sesamath'", f"{KINDS}, 'game'")


def downgrade() -> None:
    op.execute("DELETE FROM lesson_resources WHERE provider IN ('calculatice', 'sesamath') OR kind = 'game'")
    _constraints(PROVIDERS, KINDS)
