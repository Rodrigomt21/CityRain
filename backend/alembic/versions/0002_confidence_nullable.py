"""confidence nullable

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-18 00:00:00.000000

confidence passa a aceitar NULL: capturas sem imagem (gate da Jetson decidiu
"sem chuva") não têm inferência nova a reportar.

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("captures", "confidence", existing_type=sa.Float(), nullable=True)


def downgrade() -> None:
    # Preenche NULLs antes de reimpor NOT NULL, senão o ALTER falha em base com dados.
    op.execute("UPDATE captures SET confidence = 0.0 WHERE confidence IS NULL")
    op.alter_column("captures", "confidence", existing_type=sa.Float(), nullable=False)
