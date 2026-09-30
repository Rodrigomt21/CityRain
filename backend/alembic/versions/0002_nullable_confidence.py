"""nullable confidence — classificação movida para o backend

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-30 00:00:00.000000

weather_label e confidence agora são preenchidos pelo InferenceService do backend,
não mais enviados pela Jetson. confidence pode ser NULL enquanto nenhum modelo
ONNX estiver configurado.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "captures",
        "confidence",
        existing_type=sa.Float(),
        nullable=True,
    )


def downgrade() -> None:
    # Preenche NULLs com 0.0 antes de reimpor NOT NULL
    op.execute("UPDATE captures SET confidence = 0.0 WHERE confidence IS NULL")
    op.alter_column(
        "captures",
        "confidence",
        existing_type=sa.Float(),
        nullable=False,
    )
