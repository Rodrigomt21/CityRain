"""Dia ou noite no horário local (UTC−3, Brasil sem horário de verão desde 2019).

Mesma regra de ``ml/scripts/rotulagem/gerar_manifest.py``: dia = [06:00, 18:30).
As imagens de referência seca são escolhidas por período, então treino e
backend precisam concordar exatamente nesta fronteira.
"""

from datetime import datetime, time, timedelta, timezone
from typing import Literal

FUSO_LOCAL = timezone(timedelta(hours=-3))
INICIO_DIA = time(6, 0)
FIM_DIA = time(18, 30)


def periodo_local(quando: datetime) -> Literal["dia", "noite"]:
    """'dia' ou 'noite' para um instante; sem fuso, assume UTC."""
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=timezone.utc)
    hora = quando.astimezone(FUSO_LOCAL).time()
    return "dia" if INICIO_DIA <= hora < FIM_DIA else "noite"
