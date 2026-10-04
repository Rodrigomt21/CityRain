"""weather_label nullable — intensidade desconhecida é diferente de seco

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-30 00:00:00.000000

A Jetson roda um gate binário (chuva/não-chuva) e não estima intensidade.
Enquanto nenhum modelo de intensidade estiver carregado no backend, a captura
chega sem classe: weather_label fica NULL, que significa "não medido".

NULL é diferente de 'seco': 'seco' é uma afirmação sobre ausência de chuva,
gravada no único caso em que o backend pode fazê-la (a Jetson descartou a
imagem por classificar o frame como sem chuva). Não converter um no outro.

Nota sobre o CHECK: em SQL, `NULL IN (...)` resulta em NULL e um CHECK passa
quando o resultado não é FALSE — então a constraint antiga já aceitaria NULL.
Ela é recriada em forma explícita para que o schema declare a intenção e para
que o modelo SQLAlchemy e o banco não divirjam no autogenerate.

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LABELS = "'seco', 'garoa', 'moderado', 'forte'"


def upgrade() -> None:
    op.alter_column("captures", "weather_label", existing_type=sa.String(length=50), nullable=True)
    op.drop_constraint("ck_captures_weather_label", "captures", type_="check")
    op.create_check_constraint(
        "ck_captures_weather_label",
        "captures",
        f"weather_label IS NULL OR weather_label IN ({_LABELS})",
    )


def downgrade() -> None:
    # Reimpor NOT NULL exigiria decidir o que fazer com as capturas de
    # intensidade desconhecida. Convertê-las em 'seco' fabricaria medição de
    # ausência de chuva a partir de ausência de medida, e é justamente o que
    # esta migration existe para impedir. Então o downgrade falha de forma
    # explícita enquanto houver NULLs, em vez de corromper dado em silêncio.
    conn = op.get_bind()
    pendentes = conn.execute(
        sa.text("SELECT count(*) FROM captures WHERE weather_label IS NULL")
    ).scalar_one()
    if pendentes:
        raise RuntimeError(
            f"{pendentes} captura(s) com weather_label NULL. Defina uma política "
            "explícita (reclassificar com um modelo de intensidade, ou excluir "
            "essas linhas) antes de reimpor NOT NULL. Não converter para 'seco'."
        )

    op.drop_constraint("ck_captures_weather_label", "captures", type_="check")
    op.create_check_constraint(
        "ck_captures_weather_label", "captures", f"weather_label IN ({_LABELS})"
    )
    op.alter_column("captures", "weather_label", existing_type=sa.String(length=50), nullable=False)
