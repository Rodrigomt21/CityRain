"""Filtro por tipo de dispositivo compila para o SQL esperado."""

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models.capture import Capture
from app.services.capture_service import _por_tipo


def _sql(q):
    return str(q.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_fixa_exige_device_fixo():
    sql = _sql(_por_tipo(select(Capture), "fixa"))
    assert "JOIN devices" in sql and "devices.tipo = 'fixa'" in sql


def test_movel_inclui_capturas_sem_device():
    sql = _sql(_por_tipo(select(Capture), "movel"))
    assert "LEFT OUTER JOIN devices" in sql
    assert "devices.tipo = 'movel'" in sql and "captures.device_id IS NULL" in sql
