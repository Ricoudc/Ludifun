"""images des leçons (étape 27)

`lesson_images` : une image par leçon, générée sur le PC (stable-diffusion.cpp ou ComfyUI) et
montrée à l'enfant seulement après validation du parent. `ai_runs.stage` accepte `illustration`
(l'IA propose la scène, journalisée comme les autres appels). Rien à reprendre : les leçons
existantes n'ont pas d'image.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-07 22:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STAGES = "'ocr', 'analysis', 'material', 'evaluation', 'sources'"


def upgrade() -> None:
    op.create_table(
        "lesson_images",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lesson_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=True),
        sa.Column("media_type", sa.Text(), nullable=True),
        sa.Column("alt", sa.Text(), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("engine", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('generating', 'to_review', 'approved', 'rejected', 'failed')",
            name=op.f("ck_lesson_images_status"),
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"], ["lessons.id"], name=op.f("fk_lesson_images_lesson_id_lessons"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lesson_images")),
        sa.UniqueConstraint("lesson_id", name=op.f("uq_lesson_images_lesson_id")),
    )
    op.drop_constraint(op.f("ck_ai_runs_stage"), "ai_runs", type_="check")
    op.create_check_constraint(op.f("ck_ai_runs_stage"), "ai_runs", f"stage IN ({STAGES}, 'illustration')")


def downgrade() -> None:
    op.execute("DELETE FROM ai_runs WHERE stage = 'illustration'")
    op.drop_constraint(op.f("ck_ai_runs_stage"), "ai_runs", type_="check")
    op.create_check_constraint(op.f("ck_ai_runs_stage"), "ai_runs", f"stage IN ({STAGES})")
    op.drop_table("lesson_images")
