"""remove dismissed disposition

Revision ID: c0f2a3b4c5d6
Revises: b9e1f2a3c4d5
Create Date: 2026-09-14 13:56:00.000000

disposition is stored as a plain string, not a native SQL enum.
Existing dismissed rows are rewritten to deprioritized. The table schema
does not need to be recreated.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c0f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "b9e1f2a3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DISMISSED_TO_DEPRIORITIZED = sa.text(
    "UPDATE discovery_user_states "
    "SET disposition = 'deprioritized' "
    "WHERE disposition = 'dismissed'"
)


def upgrade() -> None:
    op.execute(DISMISSED_TO_DEPRIORITIZED)


def downgrade() -> None:
    # Column type is still VARCHAR. Original dismissed vs deprioritized rows
    # cannot be distinguished after upgrade, so data is left as deprioritized.
    pass
