"""ressources : Les Fondamentaux (Réseau Canopé) et Maître Lucas, en consultation seulement

`lesson_resources.provider` accepte `fondamentaux` et `maitrelucas` ; `kind` accepte `lesson`
(une page de leçon avec sa vidéo). Rien à reprendre : les ressources existantes ne changent pas.

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-09 12:00:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0027"
down_revision: str | Sequence[str] | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROVIDERS = "'mathalea', 'vikidia', 'lumni'"
KINDS = "'exercise', 'quiz', 'video', 'article'"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_lesson_resources_provider"), "lesson_resources", type_="check")
    op.create_check_constraint(
        op.f("ck_lesson_resources_provider"),
        "lesson_resources",
        f"provider IN ({PROVIDERS}, 'fondamentaux', 'maitrelucas')",
    )
    op.drop_constraint(op.f("ck_lesson_resources_kind"), "lesson_resources", type_="check")
    op.create_check_constraint(
        op.f("ck_lesson_resources_kind"), "lesson_resources", f"kind IN ({KINDS}, 'lesson')"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM lesson_resources WHERE provider IN ('fondamentaux', 'maitrelucas') OR kind = 'lesson'"
    )
    op.drop_constraint(op.f("ck_lesson_resources_kind"), "lesson_resources", type_="check")
    op.create_check_constraint(op.f("ck_lesson_resources_kind"), "lesson_resources", f"kind IN ({KINDS})")
    op.drop_constraint(op.f("ck_lesson_resources_provider"), "lesson_resources", type_="check")
    op.create_check_constraint(
        op.f("ck_lesson_resources_provider"), "lesson_resources", f"provider IN ({PROVIDERS})"
    )
