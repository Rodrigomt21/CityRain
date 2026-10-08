"""câmera fixa: tipo do dispositivo e modelo que classificou a captura

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-08 00:00:00.000000

O tipo vem do dispositivo, nunca da imagem: 'movel' (Jetson no carro, gate na
placa + modelo móvel no backend) ou 'fixa' (câmera parada, sem Jetson, modelo
fixo de 4 classes). Dispositivos existentes viram 'movel' pelo server_default.
Câmera fixa guarda a posição no cadastro (latitude/longitude) e a URL pública
de onde vem a imagem.

captures.modelo/modelo_versao registram qual ONNX classificou cada captura,
para as métricas por modelo nunca misturarem os dois domínios.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("tipo", sa.String(length=10), nullable=False, server_default="movel"))
    op.add_column("devices", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("devices", sa.Column("longitude", sa.Float(), nullable=True))
    op.add_column("devices", sa.Column("stream_url", sa.String(length=500), nullable=True))
    op.add_column("devices", sa.Column("descricao", sa.String(length=200), nullable=True))
    op.create_check_constraint("ck_devices_tipo", "devices", "tipo IN ('movel', 'fixa')")
    op.create_index("ix_devices_tipo", "devices", ["tipo"])
    op.add_column("captures", sa.Column("modelo", sa.String(length=100), nullable=True))
    op.add_column("captures", sa.Column("modelo_versao", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("captures", "modelo_versao")
    op.drop_column("captures", "modelo")
    op.drop_index("ix_devices_tipo", table_name="devices")
    op.drop_constraint("ck_devices_tipo", "devices", type_="check")
    for col in ("descricao", "stream_url", "longitude", "latitude", "tipo"):
        op.drop_column("devices", col)
