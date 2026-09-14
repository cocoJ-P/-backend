"""add discovery user states

Revision ID: b9e1f2a3c4d5
Revises: a8d0e1f2b3c4
Create Date: 2026-09-14 13:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b9e1f2a3c4d5"
down_revision: Union[str, Sequence[str], None] = "a8d0e1f2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "discovery_user_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("discovery_id", sa.Uuid(), nullable=False),
        sa.Column("enterprise_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disposition", sa.String(length=32), nullable=True),
        sa.Column("disposition_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "("
            "disposition IS NULL AND disposition_at IS NULL"
            ") OR ("
            "disposition IS NOT NULL AND disposition_at IS NOT NULL"
            ")",
            name="ck_discovery_user_states_disposition_timestamp",
        ),
        sa.ForeignKeyConstraint(["discovery_id"], ["discovery_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("discovery_id", "user_id", name="uq_discovery_user_states_discovery_user"),
    )
    with op.batch_alter_table("discovery_user_states", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_discovery_user_states_discovery_id"), ["discovery_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_discovery_user_states_enterprise_id"), ["enterprise_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_discovery_user_states_user_id"), ["user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_discovery_user_states_disposition"), ["disposition"], unique=False)
        batch_op.create_index(batch_op.f("ix_discovery_user_states_updated_at"), ["updated_at"], unique=False)
        batch_op.create_index(
            "ix_discovery_user_states_enterprise_updated_at",
            ["enterprise_id", "updated_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_discovery_user_states_enterprise_disposition_updated_at",
            ["enterprise_id", "disposition", "updated_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("discovery_user_states", schema=None) as batch_op:
        batch_op.drop_index("ix_discovery_user_states_enterprise_disposition_updated_at")
        batch_op.drop_index("ix_discovery_user_states_enterprise_updated_at")
        batch_op.drop_index(batch_op.f("ix_discovery_user_states_updated_at"))
        batch_op.drop_index(batch_op.f("ix_discovery_user_states_disposition"))
        batch_op.drop_index(batch_op.f("ix_discovery_user_states_user_id"))
        batch_op.drop_index(batch_op.f("ix_discovery_user_states_enterprise_id"))
        batch_op.drop_index(batch_op.f("ix_discovery_user_states_discovery_id"))

    op.drop_table("discovery_user_states")
