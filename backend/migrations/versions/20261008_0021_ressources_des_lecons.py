"""ressources des sites de confiance (étape 30)

`lesson_resources` : exercices MathALÉA, quiz Vikidia, vidéos et quiz Lumni proposés avec une
leçon, ouverts dans la visionneuse de l'application (rien n'est copié). Le parent peut en masquer
une ; le meilleur score d'un exercice noté est gardé. Rien à reprendre : les leçons existantes
n'en ont pas (le parent peut les faire chercher).

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-08 14:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | Sequence[str] | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lesson_resources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lesson_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("position", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("hidden", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("best_correct", sa.Integer(), nullable=True),
        sa.Column("best_total", sa.Integer(), nullable=True),
        sa.Column("last_done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "provider IN ('mathalea', 'vikidia', 'lumni')", name=op.f("ck_lesson_resources_provider")
        ),
        sa.CheckConstraint(
            "kind IN ('exercise', 'quiz', 'video', 'article')", name=op.f("ck_lesson_resources_kind")
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["lessons.id"],
            name=op.f("fk_lesson_resources_lesson_id_lessons"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lesson_resources")),
        sa.UniqueConstraint("lesson_id", "url", name=op.f("uq_lesson_resources_lesson_id_url")),
    )


def downgrade() -> None:
    op.drop_table("lesson_resources")
