"""images des notions et statut « pas utile » (étape 28)

`lesson_images` garde l'image de la leçon (`knowledge_id` vide, une par leçon) et accueille les
images des notions concrètes (une par notion, supprimée avec elle) qui servent aux jeux
« apprendre par l'image ». Nouveau statut `not_needed` : l'IA juge qu'une image n'aiderait pas
à retenir la leçon. Reprise : les images existantes sont celles des leçons, rien à changer.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-08 06:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | Sequence[str] | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_STATUSES = "'generating', 'to_review', 'approved', 'rejected', 'failed'"


def upgrade() -> None:
    op.add_column("lesson_images", sa.Column("knowledge_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_lesson_images_knowledge_id_knowledge_items"),
        "lesson_images",
        "knowledge_items",
        ["knowledge_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(op.f("uq_lesson_images_lesson_id"), "lesson_images", type_="unique")
    op.create_index(
        "uq_lesson_images_cover",
        "lesson_images",
        ["lesson_id"],
        unique=True,
        postgresql_where=sa.text("knowledge_id IS NULL"),
    )
    op.create_index(
        "uq_lesson_images_knowledge",
        "lesson_images",
        ["knowledge_id"],
        unique=True,
        postgresql_where=sa.text("knowledge_id IS NOT NULL"),
    )
    op.drop_constraint(op.f("ck_lesson_images_status"), "lesson_images", type_="check")
    op.create_check_constraint(
        op.f("ck_lesson_images_status"), "lesson_images", f"status IN ({OLD_STATUSES}, 'not_needed')"
    )


def downgrade() -> None:
    # Les images des notions et les « pas utile » n'existaient pas : on les oublie (les fichiers
    # orphelins sont effacés au démarrage du serveur).
    op.execute("DELETE FROM lesson_images WHERE knowledge_id IS NOT NULL OR status = 'not_needed'")
    op.drop_constraint(op.f("ck_lesson_images_status"), "lesson_images", type_="check")
    op.create_check_constraint(
        op.f("ck_lesson_images_status"), "lesson_images", f"status IN ({OLD_STATUSES})"
    )
    op.drop_index("uq_lesson_images_knowledge", table_name="lesson_images")
    op.drop_index("uq_lesson_images_cover", table_name="lesson_images")
    op.create_unique_constraint(op.f("uq_lesson_images_lesson_id"), "lesson_images", ["lesson_id"])
    op.drop_constraint(
        op.f("fk_lesson_images_knowledge_id_knowledge_items"), "lesson_images", type_="foreignkey"
    )
    op.drop_column("lesson_images", "knowledge_id")
