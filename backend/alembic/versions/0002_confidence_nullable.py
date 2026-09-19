"""confidence nullable

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("captures", "confidence", nullable=True)


def downgrade() -> None:
    op.alter_column("captures", "confidence", nullable=False)
