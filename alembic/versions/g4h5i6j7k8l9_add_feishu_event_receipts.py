"""add feishu event receipts

Revision ID: g4h5i6j7k8l9
Revises: f3c4d5e6f7a8
Create Date: 2026-09-15 14:20:00.000000

FeishuEventReceipt is inbound event idempotency metadata.
It does not store raw payloads and is not a business domain.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g4h5i6j7k8l9"
down_revision: Union[str, Sequence[str], None] = "f3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feishu_event_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("app_token", sa.String(length=128), nullable=True),
        sa.Column("table_id", sa.String(length=128), nullable=True),
        sa.Column("record_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('received', 'processed', 'ignored', 'failed')",
            name="ck_feishu_event_receipts_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_feishu_event_receipts_event_id"),
    )
    op.create_index("ix_feishu_event_receipts_status", "feishu_event_receipts", ["status"])
    op.create_index("ix_feishu_event_receipts_received_at", "feishu_event_receipts", ["received_at"])
    op.create_index("ix_feishu_event_receipts_record_id", "feishu_event_receipts", ["record_id"])


def downgrade() -> None:
    op.drop_index("ix_feishu_event_receipts_record_id", table_name="feishu_event_receipts")
    op.drop_index("ix_feishu_event_receipts_received_at", table_name="feishu_event_receipts")
    op.drop_index("ix_feishu_event_receipts_status", table_name="feishu_event_receipts")
    op.drop_table("feishu_event_receipts")
