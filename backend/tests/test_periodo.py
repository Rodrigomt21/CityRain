"""Dia/noite no horário local, com a mesma regra da rotulagem do ML."""

from datetime import datetime, timezone

from app.services.periodo import periodo_local


def utc(h, m=0):
    return datetime(2026, 10, 8, h, m, tzinfo=timezone.utc)


def test_meio_dia_local_e_dia():
    assert periodo_local(utc(15)) == "dia"        # 12:00 em SP


def test_limites_do_dia():
    assert periodo_local(utc(9, 0)) == "dia"      # 06:00 local, inclusivo
    assert periodo_local(utc(8, 59)) == "noite"
    assert periodo_local(utc(21, 29)) == "dia"    # 18:29 local
    assert periodo_local(utc(21, 30)) == "noite"  # 18:30 local, exclusivo


def test_data_sem_fuso_e_tratada_como_utc():
    assert periodo_local(datetime(2026, 10, 8, 15, 0)) == "dia"
