"""add submission origin and discovery bridge

Revision ID: d1a2b3c4d5e6
Revises: c0f2a3b4c5d6
Create Date: 2026-09-14 14:40:00.000000

Existing UserSubmission rows are backfilled as user_input with a null
origin_discovery_id. SQLite unique constraints treat NULL as distinct,
so ordinary user_input submissions remain unlimited.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "c0f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BACKFILL_ORIGIN = sa.text(
    "UPDATE user_submissions "
    "SET origin_type = 'user_input' "
    "WHERE origin_discovery_id IS NULL "
    "AND (origin_type IS NULL OR origin_type = '' OR origin_type = 'user_input')"
)


def upgrade() -> None:
    with op.batch_alter_table("user_submissions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "origin_type",
                sa.String(length=32),
                nullable=False,
                server_default="user_input",
            )
        )
        batch_op.add_column(sa.Column("origin_discovery_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_user_submissions_origin_discovery_id",
            "discovery_items",
            ["origin_discovery_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            batch_op.f("ix_user_submissions_origin_discovery_id"),
            ["origin_discovery_id"],
            unique=False,
        )
        batch_op.create_unique_constraint(
            "uq_user_submissions_enterprise_user_origin_discovery",
            ["enterprise_id", "user_id", "origin_discovery_id"],
        )
        batch_op.create_check_constraint(
            "ck_user_submissions_origin_consistency",
            "("
            "origin_type = 'user_input' AND origin_discovery_id IS NULL"
            ") OR ("
            "origin_type = 'discovery'"
            ")",
        )
    op.execute(BACKFILL_ORIGIN)


def downgrade() -> None:
    with op.batch_alter_table("user_submissions", schema=None) as batch_op:
        batch_op.drop_constraint("ck_user_submissions_origin_consistency", type_="check")
        batch_op.drop_constraint(
            "uq_user_submissions_enterprise_user_origin_discovery",
            type_="unique",
        )
        batch_op.drop_constraint("fk_user_submissions_origin_discovery_id", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_user_submissions_origin_discovery_id"))
        batch_op.drop_column("origin_discovery_id")
        batch_op.drop_column("origin_type")
