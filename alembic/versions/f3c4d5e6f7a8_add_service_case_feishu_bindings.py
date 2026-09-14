"""add service case feishu bindings

Revision ID: f3c4d5e6f7a8
Revises: e2b3c4d5e6f7
Create Date: 2026-09-14 16:50:00.000000

ServiceCaseFeishuBinding is integration metadata. It does not add
Feishu fields to service_cases.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "e2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "service_case_feishu_bindings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("service_case_id", sa.Uuid(), nullable=False),
        sa.Column("bitable_app_token", sa.String(length=128), nullable=False),
        sa.Column("table_id", sa.String(length=128), nullable=False),
        sa.Column("record_id", sa.String(length=128), nullable=True),
        sa.Column("sync_status", sa.String(length=32), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("last_error_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "sync_status IN ('pending', 'synced', 'failed')",
            name="ck_service_case_feishu_bindings_sync_status",
        ),
        sa.CheckConstraint(
            "("
            "sync_status IN ('pending', 'failed')"
            ") OR ("
            "sync_status = 'synced' AND record_id IS NOT NULL AND last_synced_at IS NOT NULL"
            ")",
            name="ck_service_case_feishu_bindings_synced_record",
        ),
        sa.ForeignKeyConstraint(
            ["service_case_id"],
            ["service_cases.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_case_id", name="uq_service_case_feishu_bindings_service_case_id"),
        sa.UniqueConstraint(
            "bitable_app_token",
            "table_id",
            "record_id",
            name="uq_service_case_feishu_bindings_record",
        ),
    )
    with op.batch_alter_table("service_case_feishu_bindings", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_service_case_feishu_bindings_sync_status"),
            ["sync_status"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_service_case_feishu_bindings_updated_at"),
            ["updated_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_service_case_feishu_bindings_record_id"),
            ["record_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("service_case_feishu_bindings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_service_case_feishu_bindings_record_id"))
        batch_op.drop_index(batch_op.f("ix_service_case_feishu_bindings_updated_at"))
        batch_op.drop_index(batch_op.f("ix_service_case_feishu_bindings_sync_status"))

    op.drop_table("service_case_feishu_bindings")
