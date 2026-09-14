"""add service cases

Revision ID: e2b3c4d5e6f7
Revises: d1a2b3c4d5e6
Create Date: 2026-09-14 16:10:00.000000

ServiceCase is the enterprise service matter created from a succeeded
UserSubmission. One submission can produce at most one case.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "d1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "service_cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("enterprise_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'completed', 'closed')",
            name="ck_service_cases_status",
        ),
        sa.CheckConstraint(
            "("
            "status IN ('open', 'in_progress') "
            "AND completed_at IS NULL AND closed_at IS NULL"
            ") OR ("
            "status = 'completed' AND completed_at IS NOT NULL AND closed_at IS NULL"
            ") OR ("
            "status = 'closed' AND closed_at IS NOT NULL AND completed_at IS NULL"
            ")",
            name="ck_service_cases_terminal_timestamps",
        ),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["submission_id"], ["user_submissions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("submission_id", name="uq_service_cases_submission_id"),
    )
    with op.batch_alter_table("service_cases", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_service_cases_enterprise_id"), ["enterprise_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_service_cases_created_by_user_id"),
            ["created_by_user_id"],
            unique=False,
        )
        batch_op.create_index(batch_op.f("ix_service_cases_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_service_cases_created_at"), ["created_at"], unique=False)
        batch_op.create_index(
            "ix_service_cases_enterprise_created_at",
            ["enterprise_id", "created_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_service_cases_enterprise_status_created_at",
            ["enterprise_id", "status", "created_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_service_cases_created_by_user_created_at",
            ["created_by_user_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("service_cases", schema=None) as batch_op:
        batch_op.drop_index("ix_service_cases_created_by_user_created_at")
        batch_op.drop_index("ix_service_cases_enterprise_status_created_at")
        batch_op.drop_index("ix_service_cases_enterprise_created_at")
        batch_op.drop_index(batch_op.f("ix_service_cases_created_at"))
        batch_op.drop_index(batch_op.f("ix_service_cases_status"))
        batch_op.drop_index(batch_op.f("ix_service_cases_created_by_user_id"))
        batch_op.drop_index(batch_op.f("ix_service_cases_enterprise_id"))

    op.drop_table("service_cases")
