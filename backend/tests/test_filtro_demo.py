"""Filtro de capturas de demonstração (metadata.demo) — checado no SQL gerado, sem banco."""

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models.capture import Capture
from app.services.capture_service import _sem_demo


def test_sem_demo_filtra_pela_chave_demo_do_metadata():
    sql = str(_sem_demo(select(Capture)).compile(dialect=postgresql.dialect()))
    assert "->>" in sql and "IS NULL" in sql
