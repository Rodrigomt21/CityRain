"""Retenção de imagens de fixa: arquivo ausente tolerado, lote, throttle, nunca derruba a ingestão.

A semântica contra dados reais (fixa velha apagada, recente/móvel intactas, Capture mantido)
está em tests/integracao/test_retencao_integracao.py (precisa de TEST_DATABASE_URL).
"""

from datetime import datetime, timezone

from sqlalchemy.dialects import postgresql

from app.services import retencao_service as ret


class _Resultado:
    def __init__(self, linhas):
        self._linhas = linhas

    def all(self):
        return self._linhas


class _SessaoFalsa:
    """Devolve um lote de (id, caminho) na 1ª consulta e vazio depois; registra os comandos."""

    def __init__(self, linhas):
        self.linhas = linhas
        self.comandos = []
        self.commits = 0

    async def execute(self, stmt):
        sql = str(stmt.compile(dialect=postgresql.dialect()))
        self.comandos.append(sql)
        if sql.startswith("SELECT"):
            linhas, self.linhas = self.linhas, []
            return _Resultado(linhas)
        return _Resultado([])

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


def test_consulta_so_pega_fixa_antiga():
    sessao = _SessaoFalsa([])
    import asyncio

    asyncio.run(ret.limpar_imagens_fixa(sessao, datetime(2026, 10, 13, tzinfo=timezone.utc)))
    sql = sessao.comandos[0]
    assert "devices.tipo = %(tipo_1)s" in sql and "captures.received_at < " in sql
    assert "JOIN devices" in sql


async def test_apaga_arquivo_e_linha_e_tolera_arquivo_ausente(tmp_path):
    existe = tmp_path / "a.jpg"
    existe.write_bytes(b"x")
    sumiu = tmp_path / "ja_foi.jpg"
    sessao = _SessaoFalsa([(1, str(existe)), (2, str(sumiu))])

    n = await ret.limpar_imagens_fixa(sessao)

    assert n == 2
    assert not existe.exists()
    assert any(c.startswith("DELETE FROM media_files") for c in sessao.comandos)
    assert sessao.commits == 1


async def test_falha_ao_apagar_arquivo_mantem_a_linha(tmp_path, monkeypatch):
    def quebra(caminho):
        raise PermissionError("sem permissão")

    monkeypatch.setattr(ret, "_apagar_arquivo", quebra)
    sessao = _SessaoFalsa([(1, str(tmp_path / "a.jpg"))])
    assert await ret.limpar_imagens_fixa(sessao) == 0
    assert not any(c.startswith("DELETE") for c in sessao.comandos)


async def test_throttle_roda_no_maximo_uma_vez_por_minuto(monkeypatch):
    chamadas = []

    async def falso(db):
        chamadas.append(1)
        return 0

    monkeypatch.setattr(ret, "limpar_imagens_fixa", falso)
    monkeypatch.setattr(ret, "_ultima_execucao", None)
    await ret.limpar_imagens_fixa_throttled(object())
    await ret.limpar_imagens_fixa_throttled(object())
    assert len(chamadas) == 1


async def test_throttle_nunca_propaga_erro(monkeypatch):
    async def quebra(db):
        raise RuntimeError("banco caiu")

    monkeypatch.setattr(ret, "limpar_imagens_fixa", quebra)
    monkeypatch.setattr(ret, "_ultima_execucao", None)
    await ret.limpar_imagens_fixa_throttled(_SessaoFalsa([]))  # não levanta
