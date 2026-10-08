"""Janelas secas confirmadas por várias estações, para colher `seco` no DVR."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

_P = Path(__file__).resolve().parents[1] / "scripts" / "coleta_fixa" / "recuperar_dvr.py"
sys.path.insert(0, str(_P.parent))
_spec = importlib.util.spec_from_file_location("recuperar_dvr", _P)
dvr = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = dvr
_spec.loader.exec_module(dvr)

CAM = SimpleNamespace(id="cam", lat=-23.55, lon=-46.63)
T0 = datetime(2026, 10, 9, 3, 0, tzinfo=timezone.utc)  # 00:00 local


def leituras(horas: int, chuva_em: set[int] = frozenset(), buraco_em: set[int] = frozenset(), estacoes=2):
    """Uma leitura de 10 min por estação; `chuva_em`/`buraco_em` são índices de bloco."""
    out = []
    for e in range(estacoes):
        for i in range(horas * 6):
            if i in buraco_em:
                continue
            ts = T0 + timedelta(minutes=10 * (i + 1))
            out.append({"estacao_id": f"E{e}", "lat": -23.55 + 0.005 * e, "lon": -46.63,
                        "ts_utc": ts.isoformat(), "acumulado_mm": "0.4" if i in chuva_em else "0", "janela_min": "10"})
    return out


def test_dia_todo_seco_rende_janelas_de_dia_e_de_noite():
    js = dvr.janelas_secas(CAM, leituras(24), 5.0, T0, T0 + timedelta(hours=24), max_janelas=4)
    assert len(js) == 4
    periodos = {dvr.periodo_local(a) for a, _ in js}
    assert periodos == {"dia", "noite"}
    assert all(b - a == timedelta(minutes=30) for a, b in js)
    assert all(js[i][1] <= js[i + 1][0] for i in range(len(js) - 1))


def test_chuva_afasta_a_janela_pela_folga():
    chuva = set(range(18, 24))  # 03:00–04:00 UTC+0 depois de T0
    js = dvr.janelas_secas(CAM, leituras(8, chuva_em=chuva), 5.0, T0, T0 + timedelta(hours=8), max_janelas=10)
    inicio_chuva, fim_chuva = T0 + timedelta(hours=3), T0 + timedelta(hours=4)
    for a, b in js:
        assert b + timedelta(minutes=60) <= inicio_chuva or a - timedelta(minutes=60) >= fim_chuva


def test_buraco_de_dado_nao_vira_seco():
    js = dvr.janelas_secas(CAM, leituras(3, buraco_em=set(range(0, 18))), 5.0, T0, T0 + timedelta(hours=3))
    assert js == []


def test_uma_estacao_so_nao_basta():
    assert dvr.janelas_secas(CAM, leituras(24, estacoes=1), 5.0, T0, T0 + timedelta(hours=24)) == []


def test_estacao_longe_nao_conta():
    longe = [dict(r, lat=-24.5) for r in leituras(24)]
    assert dvr.janelas_secas(CAM, longe, 5.0, T0, T0 + timedelta(hours=24)) == []
