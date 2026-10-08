"""Migração 0004: tipo do dispositivo e modelo da captura."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


async def test_colunas_novas_existem(db):
    cols = (await db.execute(text(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_name IN ('devices', 'captures')"
    ))).all()
    nomes = {(t, c) for t, c in cols}
    for esperado in [("devices", "tipo"), ("devices", "latitude"), ("devices", "longitude"),
                     ("devices", "stream_url"), ("devices", "descricao"),
                     ("captures", "modelo"), ("captures", "modelo_versao")]:
        assert esperado in nomes


async def test_device_sem_tipo_vira_movel(db):
    await db.execute(text(
        "INSERT INTO devices (name, api_key_hash, is_active) VALUES ('legado-0004', 'h0004', true)"
    ))
    tipo = (await db.execute(text("SELECT tipo FROM devices WHERE name = 'legado-0004'"))).scalar_one()
    await db.rollback()
    assert tipo == "movel"


async def test_tipo_invalido_e_recusado(db):
    with pytest.raises(IntegrityError):
        await db.execute(text(
            "INSERT INTO devices (name, api_key_hash, is_active, tipo) VALUES ('x-0004', 'hx0004', true, 'drone')"
        ))
    await db.rollback()
