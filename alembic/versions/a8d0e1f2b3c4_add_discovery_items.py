"""add discovery items

Revision ID: a8d0e1f2b3c4
Revises: f7c8d9e0a1b2
Create Date: 2026-09-14 12:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a8d0e1f2b3c4"
down_revision: Union[str, Sequence[str], None] = "f7c8d9e0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "discovery_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("enterprise_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("reference_type", sa.String(length=32), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=True),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("opportunity_type", sa.String(length=64), nullable=True),
        sa.Column("issuer", sa.String(length=255), nullable=True),
        sa.Column("region", sa.String(length=255), nullable=True),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.Column("reference_url", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "("
            "reference_type = 'manual' AND opportunity_id IS NULL AND source_id IS NULL"
            ") OR ("
            "reference_type = 'opportunity' AND source_id IS NULL"
            ") OR ("
            "reference_type = 'source' AND opportunity_id IS NULL"
            ")",
            name="ck_discovery_items_reference_consistency",
        ),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_id"], ["opportunity_sources.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("discovery_items", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_discovery_items_enterprise_id"), ["enterprise_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_discovery_items_created_by_user_id"), ["created_by_user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_discovery_items_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_discovery_items_priority"), ["priority"], unique=False)
        batch_op.create_index(batch_op.f("ix_discovery_items_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_discovery_items_opportunity_id"), ["opportunity_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_discovery_items_source_id"), ["source_id"], unique=False)
        batch_op.create_index(
            "ix_discovery_items_enterprise_status_created_at",
            ["enterprise_id", "status", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("discovery_items", schema=None) as batch_op:
        batch_op.drop_index("ix_discovery_items_enterprise_status_created_at")
        batch_op.drop_index(batch_op.f("ix_discovery_items_source_id"))
        batch_op.drop_index(batch_op.f("ix_discovery_items_opportunity_id"))
        batch_op.drop_index(batch_op.f("ix_discovery_items_created_at"))
        batch_op.drop_index(batch_op.f("ix_discovery_items_priority"))
        batch_op.drop_index(batch_op.f("ix_discovery_items_status"))
        batch_op.drop_index(batch_op.f("ix_discovery_items_created_by_user_id"))
        batch_op.drop_index(batch_op.f("ix_discovery_items_enterprise_id"))

    op.drop_table("discovery_items")
