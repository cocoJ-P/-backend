"""add intelligence runs

Revision ID: d1e4b44a1000
Revises: 708c0e5dcb84
Create Date: 2026-09-12 22:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1e4b44a1000"
down_revision: Union[str, Sequence[str], None] = "708c0e5dcb84"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "intelligence_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("ingestion_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("analysis_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("rule_version", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("rule_result_json", sa.JSON(), nullable=True),
        sa.Column("intelligence_result_json", sa.JSON(), nullable=True),
        sa.Column("usage_json", sa.JSON(), nullable=True),
        sa.Column("input_char_count", sa.Integer(), nullable=False),
        sa.Column("input_truncated", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ingestion_id"], ["ingested_contents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["opportunity_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("intelligence_runs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_intelligence_runs_source_id"), ["source_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_intelligence_runs_ingestion_id"), ["ingestion_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_intelligence_runs_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_intelligence_runs_created_at"), ["created_at"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_intelligence_runs_analysis_fingerprint"),
            ["analysis_fingerprint"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("intelligence_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_intelligence_runs_analysis_fingerprint"))
        batch_op.drop_index(batch_op.f("ix_intelligence_runs_created_at"))
        batch_op.drop_index(batch_op.f("ix_intelligence_runs_status"))
        batch_op.drop_index(batch_op.f("ix_intelligence_runs_ingestion_id"))
        batch_op.drop_index(batch_op.f("ix_intelligence_runs_source_id"))

    op.drop_table("intelligence_runs")
