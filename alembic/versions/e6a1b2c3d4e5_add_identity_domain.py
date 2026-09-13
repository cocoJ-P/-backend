"""add identity domain

Revision ID: e6a1b2c3d4e5
Revises: d1e4b44a1000
Create Date: 2026-09-13 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e6a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "d1e4b44a1000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_users_status"), ["status"], unique=False)

    op.create_table(
        "enterprise_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("enterprise_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "enterprise_id",
            name="uq_enterprise_member_user_enterprise",
        ),
    )
    with op.batch_alter_table("enterprise_members", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_enterprise_members_user_id"),
            ["user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_enterprise_members_enterprise_id"),
            ["enterprise_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_enterprise_members_status"),
            ["status"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("enterprise_members", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_enterprise_members_status"))
        batch_op.drop_index(batch_op.f("ix_enterprise_members_enterprise_id"))
        batch_op.drop_index(batch_op.f("ix_enterprise_members_user_id"))

    op.drop_table("enterprise_members")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_status"))

    op.drop_table("users")
