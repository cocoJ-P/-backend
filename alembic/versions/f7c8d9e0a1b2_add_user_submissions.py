"""add user submissions

Revision ID: f7c8d9e0a1b2
Revises: e6a1b2c3d4e5
Create Date: 2026-09-13 23:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f7c8d9e0a1b2"
down_revision: Union[str, Sequence[str], None] = "e6a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_submissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("enterprise_id", sa.Uuid(), nullable=False),
        sa.Column("input_type", sa.String(length=16), nullable=False),
        sa.Column("input_content", sa.Text(), nullable=False),
        sa.Column("input_preview", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("failure_stage", sa.String(length=16), nullable=True),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("ingestion_id", sa.Uuid(), nullable=True),
        sa.Column("intelligence_run_id", sa.Uuid(), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_id"], ["opportunity_sources.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["ingestion_id"], ["ingested_contents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["intelligence_run_id"], ["intelligence_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("user_submissions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_user_submissions_user_id"), ["user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_user_submissions_enterprise_id"), ["enterprise_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_user_submissions_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_user_submissions_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_user_submissions_source_id"), ["source_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_user_submissions_ingestion_id"), ["ingestion_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_user_submissions_intelligence_run_id"),
            ["intelligence_run_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_user_submissions_enterprise_created_at",
            ["enterprise_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("user_submissions", schema=None) as batch_op:
        batch_op.drop_index("ix_user_submissions_enterprise_created_at")
        batch_op.drop_index(batch_op.f("ix_user_submissions_intelligence_run_id"))
        batch_op.drop_index(batch_op.f("ix_user_submissions_ingestion_id"))
        batch_op.drop_index(batch_op.f("ix_user_submissions_source_id"))
        batch_op.drop_index(batch_op.f("ix_user_submissions_created_at"))
        batch_op.drop_index(batch_op.f("ix_user_submissions_status"))
        batch_op.drop_index(batch_op.f("ix_user_submissions_enterprise_id"))
        batch_op.drop_index(batch_op.f("ix_user_submissions_user_id"))

    op.drop_table("user_submissions")
