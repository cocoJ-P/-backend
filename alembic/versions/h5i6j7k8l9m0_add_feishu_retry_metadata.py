"""add feishu retry metadata

Revision ID: h5i6j7k8l9m0
Revises: g4h5i6j7k8l9
Create Date: 2026-09-15 15:50:00.000000

Retry/reconciliation metadata for Binding and EventReceipt.
Existing rows keep retry_count=0. Does not change sync_status or Domain.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h5i6j7k8l9m0"
down_revision: Union[str, Sequence[str], None] = "g4h5i6j7k8l9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "service_case_feishu_bindings",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "service_case_feishu_bindings",
        sa.Column("last_retry_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "service_case_feishu_bindings",
        sa.Column(
            "last_error_retryable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "feishu_event_receipts",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "feishu_event_receipts",
        sa.Column("last_retry_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "feishu_event_receipts",
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("feishu_event_receipts", "retryable")
    op.drop_column("feishu_event_receipts", "last_retry_at")
    op.drop_column("feishu_event_receipts", "retry_count")
    op.drop_column("service_case_feishu_bindings", "last_error_retryable")
    op.drop_column("service_case_feishu_bindings", "last_retry_at")
    op.drop_column("service_case_feishu_bindings", "retry_count")
