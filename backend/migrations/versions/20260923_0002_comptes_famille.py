"""comptes famille : parents, familles, enfants, appareils liés, codes de liaison

Les données de 0001 appartenaient à des appareils anonymes sans enfant associé ;
aucune n'existe en production (rien n'a été déployé). Elles sont supprimées ici.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-23 14:28:16.543732

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("TRUNCATE devices, learners, lessons, sessions, knowledge_mastery CASCADE")
    op.create_table(
        "families",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_families")),
    )
    op.create_table(
        "parents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("privacy_accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_parents")),
        sa.UniqueConstraint("email", name=op.f("uq_parents_email")),
    )
    op.create_table(
        "children",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("grade", sa.Text(), nullable=False),
        sa.Column("avatar", sa.Text(), nullable=True),
        sa.Column("parental_consent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["family_id"], ["families.id"], name=op.f("fk_children_family_id_families"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_children")),
    )
    op.create_index(op.f("ix_children_family_id"), "children", ["family_id"], unique=False)
    op.create_table(
        "family_members",
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.CheckConstraint("role IN ('owner', 'member')", name=op.f("ck_family_members_role")),
        sa.ForeignKeyConstraint(
            ["family_id"],
            ["families.id"],
            name=op.f("fk_family_members_family_id_families"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["parents.id"],
            name=op.f("fk_family_members_parent_id_parents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("family_id", "parent_id", name=op.f("pk_family_members")),
    )
    op.create_index(op.f("ix_family_members_parent_id"), "family_members", ["parent_id"], unique=False)
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["parents.id"],
            name=op.f("fk_password_reset_tokens_parent_id_parents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_reset_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_password_reset_tokens_token_hash")),
    )
    op.create_index(
        op.f("ix_password_reset_tokens_parent_id"), "password_reset_tokens", ["parent_id"], unique=False
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["parents.id"],
            name=op.f("fk_refresh_tokens_parent_id_parents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by"],
            ["refresh_tokens.id"],
            name=op.f("fk_refresh_tokens_replaced_by_refresh_tokens"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
    )
    op.create_index(op.f("ix_refresh_tokens_parent_id"), "refresh_tokens", ["parent_id"], unique=False)
    op.create_table(
        "link_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("child_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.LargeBinary(), nullable=False),
        sa.Column("qr_token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["child_id"], ["children.id"], name=op.f("fk_link_codes_child_id_children"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_link_codes")),
        sa.UniqueConstraint("qr_token_hash", name=op.f("uq_link_codes_qr_token_hash")),
    )
    op.create_index(op.f("ix_link_codes_child_id"), "link_codes", ["child_id"], unique=False)
    op.create_index(op.f("ix_link_codes_code_hash"), "link_codes", ["code_hash"], unique=False)
    op.add_column("devices", sa.Column("child_id", sa.Uuid(), nullable=False))
    op.add_column("devices", sa.Column("name", sa.Text(), nullable=True))
    op.add_column("devices", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_devices_child_id"), "devices", ["child_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_devices_child_id_children"), "devices", "children", ["child_id"], ["id"], ondelete="CASCADE"
    )
    op.add_column("knowledge_mastery", sa.Column("child_id", sa.Uuid(), nullable=False))
    op.drop_index(op.f("ix_knowledge_mastery_due"), table_name="knowledge_mastery")
    op.create_index(
        "ix_knowledge_mastery_due", "knowledge_mastery", ["child_id", "next_review_at"], unique=False
    )
    op.drop_constraint(
        op.f("fk_knowledge_mastery_learner_id_learners"), "knowledge_mastery", type_="foreignkey"
    )
    op.create_foreign_key(
        op.f("fk_knowledge_mastery_child_id_children"),
        "knowledge_mastery",
        "children",
        ["child_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_column("knowledge_mastery", "learner_id")
    op.add_column("lessons", sa.Column("child_id", sa.Uuid(), nullable=False))
    op.drop_index(op.f("ix_lessons_learner_recent"), table_name="lessons")
    op.create_index(
        "ix_lessons_child_recent", "lessons", ["child_id", sa.literal_column("created_at DESC")], unique=False
    )
    op.drop_constraint(op.f("fk_lessons_learner_id_learners"), "lessons", type_="foreignkey")
    op.create_foreign_key(
        op.f("fk_lessons_child_id_children"), "lessons", "children", ["child_id"], ["id"], ondelete="CASCADE"
    )
    op.drop_column("lessons", "learner_id")
    op.add_column("sessions", sa.Column("child_id", sa.Uuid(), nullable=False))
    op.drop_index(op.f("ix_sessions_learner_recent"), table_name="sessions")
    op.create_index(
        "ix_sessions_child_recent",
        "sessions",
        ["child_id", sa.literal_column("started_at DESC")],
        unique=False,
    )
    op.drop_constraint(op.f("fk_sessions_learner_id_learners"), "sessions", type_="foreignkey")
    op.create_foreign_key(
        op.f("fk_sessions_child_id_children"),
        "sessions",
        "children",
        ["child_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_column("sessions", "learner_id")
    # Plus aucune clé étrangère ne pointe vers learners.
    op.drop_index(op.f("ix_learners_device_id"), table_name="learners")
    op.drop_table("learners")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("TRUNCATE parents, families, children, devices, lessons, sessions, knowledge_mastery CASCADE")
    op.create_table(
        "learners",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("device_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("display_name", sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.id"], name=op.f("fk_learners_device_id_devices"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_learners")),
    )
    op.create_index(op.f("ix_learners_device_id"), "learners", ["device_id"], unique=False)
    op.add_column("sessions", sa.Column("learner_id", sa.UUID(), autoincrement=False, nullable=False))
    op.drop_constraint(op.f("fk_sessions_child_id_children"), "sessions", type_="foreignkey")
    op.create_foreign_key(
        op.f("fk_sessions_learner_id_learners"),
        "sessions",
        "learners",
        ["learner_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_index("ix_sessions_child_recent", table_name="sessions")
    op.create_index(
        op.f("ix_sessions_learner_recent"),
        "sessions",
        ["learner_id", sa.literal_column("started_at DESC")],
        unique=False,
    )
    op.drop_column("sessions", "child_id")
    op.add_column("lessons", sa.Column("learner_id", sa.UUID(), autoincrement=False, nullable=False))
    op.drop_constraint(op.f("fk_lessons_child_id_children"), "lessons", type_="foreignkey")
    op.create_foreign_key(
        op.f("fk_lessons_learner_id_learners"),
        "lessons",
        "learners",
        ["learner_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_index("ix_lessons_child_recent", table_name="lessons")
    op.create_index(
        op.f("ix_lessons_learner_recent"),
        "lessons",
        ["learner_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.drop_column("lessons", "child_id")
    op.add_column(
        "knowledge_mastery", sa.Column("learner_id", sa.UUID(), autoincrement=False, nullable=False)
    )
    op.drop_constraint(
        op.f("fk_knowledge_mastery_child_id_children"), "knowledge_mastery", type_="foreignkey"
    )
    op.create_foreign_key(
        op.f("fk_knowledge_mastery_learner_id_learners"),
        "knowledge_mastery",
        "learners",
        ["learner_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_index("ix_knowledge_mastery_due", table_name="knowledge_mastery")
    op.create_index(
        op.f("ix_knowledge_mastery_due"), "knowledge_mastery", ["learner_id", "next_review_at"], unique=False
    )
    op.drop_column("knowledge_mastery", "child_id")
    op.drop_constraint(op.f("fk_devices_child_id_children"), "devices", type_="foreignkey")
    op.drop_index(op.f("ix_devices_child_id"), table_name="devices")
    op.drop_column("devices", "revoked_at")
    op.drop_column("devices", "name")
    op.drop_column("devices", "child_id")
    op.drop_index(op.f("ix_link_codes_code_hash"), table_name="link_codes")
    op.drop_index(op.f("ix_link_codes_child_id"), table_name="link_codes")
    op.drop_table("link_codes")
    op.drop_index(op.f("ix_refresh_tokens_parent_id"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index(op.f("ix_password_reset_tokens_parent_id"), table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_index(op.f("ix_family_members_parent_id"), table_name="family_members")
    op.drop_table("family_members")
    op.drop_index(op.f("ix_children_family_id"), table_name="children")
    op.drop_table("children")
    op.drop_table("parents")
    op.drop_table("families")
