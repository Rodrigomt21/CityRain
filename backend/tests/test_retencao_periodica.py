"""Retenção periódica (lifespan): roda sem ingestão, nunca propaga erro e repete no intervalo."""

import asyncio

import pytest

from app.services import retencao_service as ret


class _SessaoCtx:
    """Fábrica de sessão falsa: `async with fabrica() as db` devolve um objeto qualquer."""

    def __init__(self, registro):
        self.registro = registro

    async def __aenter__(self):
        self.registro.append("abriu")
        return object()

    async def __aexit__(self, *exc):
        self.registro.append("fechou")
        return False


async def test_rodar_uma_vez_abre_sessao_propria_e_devolve_o_total(monkeypatch):
    registro = []

    async def falso(db):
        return 3

    monkeypatch.setattr(ret, "limpar_imagens_fixa", falso)
    assert await ret.rodar_uma_vez(lambda: _SessaoCtx(registro)) == 3
    assert registro == ["abriu", "fechou"]


async def test_rodar_uma_vez_nunca_propaga_erro(monkeypatch):
    async def quebra(db):
        raise RuntimeError("banco caiu")

    monkeypatch.setattr(ret, "limpar_imagens_fixa", quebra)
    assert await ret.rodar_uma_vez(lambda: _SessaoCtx([])) == 0


async def test_tarefa_periodica_repete_ate_ser_cancelada(monkeypatch):
    chamadas = []

    async def falso(fabrica):
        chamadas.append(1)
        return 0

    monkeypatch.setattr(ret, "rodar_uma_vez", falso)
    tarefa = asyncio.create_task(ret.tarefa_periodica(lambda: None, 0.01))
    await asyncio.sleep(0.05)
    tarefa.cancel()
    with pytest.raises(asyncio.CancelledError):
        await tarefa
    assert len(chamadas) >= 2
