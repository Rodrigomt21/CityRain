"""Testes de `gps.py` para J7 (`hora_rmc_utc`) e J8 (`ultimo_fix_em`).

Motivação registrada em docs/specs/spec-pipeline-jetson.md (J7/J8): a Jetson
não tem RTC utilizável (`fake-hwclock` é só um paliativo) — sem uma segunda
fonte de tempo independente do relógio do sistema, um NTP que não sincronizou
antes da captura corrompe `capturado_em_utc` sem deixar rastro (isso
inutilizou 19.037 frames em maio). E sem saber a idade do último fix, uma
coordenada de dias atrás pode ser usada como se fosse fresca (caso real
observado em 23/09: 7 dias de defasagem sem nenhum campo que denunciasse).

As sentenças NMEA usadas aqui são sintéticas, com checksum calculado pelo
próprio teste (`nmea()`) em vez de coladas prontas — colar um exemplo com
checksum errado faria `pynmea2.parse` rejeitar a sentença e o teste acabaria
exercitando o caminho de erro em vez do caso pretendido.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

# `gps.py` vive fora de um pacote Python instalável, mesmo padrão de
# test_normalizacao.py e test_uploader.py: carrega o módulo direto do
# arquivo pelo caminho.
_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "captura" / "gps.py"
_spec = importlib.util.spec_from_file_location("gps", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
gps = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = gps
_spec.loader.exec_module(gps)


def nmea(corpo: str) -> str:
    """Monta uma sentença NMEA (`$corpo*checksum`) com checksum calculado.

    O checksum NMEA é o XOR de todos os bytes entre `$` e `*`.
    """
    checksum = 0
    for c in corpo:
        checksum ^= ord(c)
    return f"${corpo}*{checksum:02X}"


def gga_com_fix(
    *,
    qualidade: str = "1",
    satelites: str = "08",
    hdop: str = "0.9",
    hora: str = "124928.00",
) -> str:
    """GGA com fix válido, coordenadas fixas de teste (Sé, SP)."""
    corpo = (
        f"GPGGA,{hora},2333.9000,S,04628.5000,W,{qualidade},"
        f"{satelites},{hdop},760.0,M,-3.0,M,,"
    )
    return nmea(corpo)


def gga_sem_fix(hora: str = "124930.00") -> str:
    """GGA sem fix (qualidade 0), como um receptor real reporta: campos de
    posição em branco — o parser precisa ignorá-los, não usá-los."""
    corpo = f"GPGGA,{hora},,,,,0,00,,,M,,M,,"
    return nmea(corpo)


def rmc(*, status: str = "A", hora: str = "124928.00", data: str = "230926") -> str:
    corpo = f"GPRMC,{hora},{status},2333.9000,S,04628.5000,W,0.5,54.7,{data},,,A"
    return nmea(corpo)


class SentinelaFimDeTeste(Exception):
    """Levantada pelos dublês de `main()` para interromper o laço infinito no
    ponto exato que o teste precisa inspecionar — nunca é confundida com uma
    condição real do domínio (não é `SerialException` nem erro de parsing)."""


class SerialExceptionFalsa(Exception):
    """Substitui `serial.SerialException` nesta suíte. Só o nome importa: o
    `except serial.SerialException` de `gps.py` casa por identidade de classe
    depois que `gps.serial` é trocado pelo módulo falso via monkeypatch."""


class _PortaSerialFalsa:
    """Simula `with serial.Serial(...) as ser:` a partir de uma lista de
    "ações": `bytes` é devolvido por `readline()`, uma instância de exceção é
    levantada por `readline()`."""

    def __init__(self, acoes):
        self._acoes = list(acoes)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def readline(self):
        acao = self._acoes.pop(0)
        if isinstance(acao, BaseException):
            raise acao
        return acao


def _monta_serial_falso(acoes):
    return types.SimpleNamespace(
        Serial=lambda *a, **k: _PortaSerialFalsa(acoes),
        SerialException=SerialExceptionFalsa,
    )


# ============================================================
# estado_inicial()
# ============================================================


def test_estado_inicial_tem_campos_novos_como_none():
    estado = gps.estado_inicial()
    assert estado["hora_rmc_utc"] is None
    assert estado["ultimo_fix_em"] is None


# ============================================================
# J7 — hora_rmc_utc
# ============================================================


def test_rmc_status_a_preenche_hora_rmc_utc_em_utc_iso():
    estado = gps.estado_inicial()
    ok = gps.processa_linha(rmc(status="A", hora="124928.00", data="230926"), estado)
    assert ok is True
    assert estado["status_rmc"] == "A"
    assert estado["hora_rmc_utc"] == "2026-09-23T12:49:28+00:00"


def test_rmc_status_v_nao_preenche_hora_rmc_utc():
    estado = gps.estado_inicial()
    ok = gps.processa_linha(rmc(status="V", hora="124928.00", data="230926"), estado)
    assert ok is True
    assert estado["status_rmc"] == "V"
    assert estado["hora_rmc_utc"] is None


# ============================================================
# J8 — ultimo_fix_em
# ============================================================


def test_gga_com_fix_preenche_ultimo_fix_em_e_coordenadas():
    estado = gps.estado_inicial()
    ok = gps.processa_linha(gga_com_fix(), estado)
    assert ok is True
    assert estado["fix"] is True
    assert estado["latitude"] is not None
    assert estado["longitude"] is not None
    assert estado["ultimo_fix_em"] is not None


def test_gga_sem_fix_preserva_coordenadas_e_congela_ultimo_fix_em():
    estado = gps.estado_inicial()
    gps.processa_linha(gga_com_fix(), estado)
    lat_antes = estado["latitude"]
    lon_antes = estado["longitude"]
    fix_em_antes = estado["ultimo_fix_em"]
    assert fix_em_antes is not None

    ok = gps.processa_linha(gga_sem_fix(), estado)

    assert ok is True
    assert estado["fix"] is False
    # a posição anterior é útil e não deve ser apagada...
    assert estado["latitude"] == lat_antes
    assert estado["longitude"] == lon_antes
    # ...mas o registro de quando ela foi vista precisa congelar, senão não
    # há como saber que essa coordenada é velha.
    assert estado["ultimo_fix_em"] == fix_em_antes


def test_fix_recuperado_volta_a_avancar_ultimo_fix_em():
    estado = gps.estado_inicial()
    gps.processa_linha(gga_com_fix(hora="124928.00"), estado)
    fix_em_antes = estado["ultimo_fix_em"]

    gps.processa_linha(gga_sem_fix(hora="124930.00"), estado)
    assert estado["ultimo_fix_em"] == fix_em_antes  # ainda congelado

    ok = gps.processa_linha(gga_com_fix(hora="124932.00"), estado)
    assert ok is True
    assert estado["fix"] is True
    # religou: ultimo_fix_em volta a se mexer (não fica preso para sempre no
    # primeiro fix da sessão).
    assert estado["ultimo_fix_em"] is not None


# ============================================================
# Robustez — sentença malformada não derruba nem corrompe o estado
# ============================================================


def test_linha_sem_cifrao_e_ignorada():
    estado = gps.estado_inicial()
    ok = gps.processa_linha("isso nao e uma sentenca NMEA", estado)
    assert ok is False
    assert estado == gps.estado_inicial()


def test_checksum_invalido_nao_altera_estado():
    estado = gps.estado_inicial()
    gps.processa_linha(gga_com_fix(), estado)  # popula um fix bom conhecido
    estado_antes = dict(estado)

    linha_boa = gga_com_fix(hora="124931.00")
    linha_corrompida = linha_boa[:-2] + "00"  # adultera o checksum de propósito
    assert linha_corrompida != linha_boa

    ok = gps.processa_linha(linha_corrompida, estado)

    assert ok is False
    assert estado == estado_antes


def test_campo_com_formato_inesperado_nao_corrompe_estado_parcialmente():
    """Regressão: um receptor não conforme pode entregar um campo isolado em
    formato inesperado (checksum válido, ex. hdop vindo como texto). Antes da
    correção deste J7/J8, `fix`/`satelites` já tinham sido escritos em
    `estado` quando a conversão de `hdop` falhava mais adiante — deixando
    lat/lon/ultimo_fix_em atrasados atrás de um `fix=True` que não reflete
    nenhuma leitura completa e válida. Ou a sentença inteira é aplicada, ou
    nada dela é.
    """
    estado = gps.estado_inicial()
    gps.processa_linha(gga_com_fix(satelites="08"), estado)  # fix bom conhecido
    estado_antes = dict(estado)

    # satélites=05 (diferente do fix anterior) para que uma mutação parcial
    # antes do `float("ABC")` estourar fique observável — se `satelites`
    # tivesse o mesmo valor de antes, uma correção que só mutasse os campos
    # que "coincidem" passaria despercebida.
    linha_malformada = nmea(
        "GPGGA,124935.00,2333.9000,S,04628.5000,W,1,05,ABC,760.0,M,-3.0,M,,"
    )
    ok = gps.processa_linha(linha_malformada, estado)

    assert ok is False
    assert estado == estado_antes


def test_sequencia_com_linha_invalida_no_meio_preserva_estado_final():
    estado = gps.estado_inicial()
    gps.processa_linha(gga_com_fix(), estado)
    gps.processa_linha("lixo qualquer sem cifrao", estado)
    gps.processa_linha(rmc(status="A"), estado)

    assert estado["fix"] is True
    assert estado["hora_rmc_utc"] is not None


# ============================================================
# J8 (explícito) — degradação por silêncio e reconexão não limpam
# hora_rmc_utc nem ultimo_fix_em, só `fix`.
#
# `main()` tem laço infinito e abre a porta serial de verdade, então os dois
# testes abaixo rodam `gps.main()` de verdade, com `gps.serial` trocado por um
# dublê (mesmo padrão de stub de módulo de test_uploader.py) e uma exceção
# sentinela para escapar do laço no ponto exato que se quer inspecionar.
# ============================================================


def test_silencio_prolongado_nao_limpa_hora_rmc_nem_ultimo_fix(monkeypatch):
    estados_salvos = []
    monkeypatch.setattr(
        gps, "salvar_estado", lambda estado: estados_salvos.append(dict(estado))
    )

    # 4 chamadas a time.monotonic(): ultima_valida inicial, após o GGA válido,
    # após o RMC válido, e a checagem de silêncio (que precisa acusar mais de
    # SILENCIO_MAX_S desde a última linha válida).
    valores_monotonic = iter([0.0, 0.0, 0.0, gps.SILENCIO_MAX_S + 1.0])
    monkeypatch.setattr(gps.time, "monotonic", lambda: next(valores_monotonic))

    acoes = [
        gga_com_fix().encode("ascii"),
        rmc(status="A").encode("ascii"),
        b"",  # silêncio (timeout do readline, sem dado nenhum)
        SentinelaFimDeTeste("fim do teste — já degradou o fix"),
    ]
    monkeypatch.setattr(gps, "serial", _monta_serial_falso(acoes))

    with pytest.raises(SentinelaFimDeTeste):
        gps.main()

    # ordem dos salvar_estado(): inicial, após GGA, após RMC, após degradar.
    assert len(estados_salvos) == 4
    estado_apos_gga, estado_apos_rmc, estado_degradado = (
        estados_salvos[1],
        estados_salvos[2],
        estados_salvos[3],
    )
    assert estado_apos_gga["fix"] is True
    assert estado_apos_rmc["hora_rmc_utc"] is not None

    assert estado_degradado["fix"] is False
    assert estado_degradado["hora_rmc_utc"] == estado_apos_rmc["hora_rmc_utc"]
    assert estado_degradado["ultimo_fix_em"] == estado_apos_gga["ultimo_fix_em"]
    assert estado_degradado["latitude"] == estado_apos_gga["latitude"]


def test_serial_exception_nao_limpa_hora_rmc_nem_ultimo_fix(monkeypatch):
    estados_salvos = []
    monkeypatch.setattr(
        gps, "salvar_estado", lambda estado: estados_salvos.append(dict(estado))
    )
    monkeypatch.setattr(gps.time, "monotonic", lambda: 0.0)

    def dorme_e_para(segundos):
        # substitui o RECONNECT_DELAY_S real: levanta a sentinela em vez de
        # esperar de verdade, e o outer `while True` nunca chega a reabrir a porta.
        raise SentinelaFimDeTeste("fim do teste — já tratou a SerialException")

    monkeypatch.setattr(gps.time, "sleep", dorme_e_para)

    acoes = [
        gga_com_fix().encode("ascii"),
        rmc(status="A").encode("ascii"),
        SerialExceptionFalsa("porta serial sumiu"),
    ]
    monkeypatch.setattr(gps, "serial", _monta_serial_falso(acoes))

    with pytest.raises(SentinelaFimDeTeste):
        gps.main()

    assert len(estados_salvos) == 4  # inicial, GGA, RMC, após a exceção
    estado_apos_gga, estado_apos_rmc, estado_apos_excecao = (
        estados_salvos[1],
        estados_salvos[2],
        estados_salvos[3],
    )

    assert estado_apos_excecao["fix"] is False
    assert estado_apos_excecao["hora_rmc_utc"] == estado_apos_rmc["hora_rmc_utc"]
    assert estado_apos_excecao["ultimo_fix_em"] == estado_apos_gga["ultimo_fix_em"]
    assert estado_apos_excecao["latitude"] == estado_apos_gga["latitude"]
