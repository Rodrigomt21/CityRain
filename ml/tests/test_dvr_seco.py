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


def leituras_horarias(horas: int, estacoes: int = 3, minuto: int = 50, sem_hora: dict[int, set[int]] | None = None,
                      chuva_10min: dict[int, set[int]] | None = None):
    """Cadência REAL do CEMADEN/PED: seco = 1 leitura zerada por hora (janela_min=10).

    `sem_hora[e]` = horas (índice desde T0) em que a estação `e` não mandou leitura;
    `chuva_10min[e]` = índices de bloco de 10 min com chuva (leituras de 10 min extras).
    """
    sem_hora, chuva_10min = sem_hora or {}, chuva_10min or {}
    out = []
    for e in range(estacoes):
        base = {"estacao_id": f"E{e}", "lat": -23.55 + 0.004 * e, "lon": -46.63, "janela_min": "10"}
        for h in range(horas):
            if h in sem_hora.get(e, set()):
                continue
            ts = T0 + timedelta(hours=h, minutes=minuto)
            out.append({**base, "ts_utc": ts.isoformat(), "acumulado_mm": "0.0"})
        for i in chuva_10min.get(e, set()):
            ts = T0 + timedelta(minutes=10 * (i + 1))
            out.append({**base, "ts_utc": ts.isoformat(), "acumulado_mm": "0.4"})
    return out


def test_cadencia_real_horaria_rende_janelas():
    """Regressão do achado crítico: com zeros horários a regra antiga dava zero janelas."""
    js = dvr.janelas_secas(CAM, leituras_horarias(24), 5.0, T0, T0 + timedelta(hours=24))
    assert js
    assert all(b - a == timedelta(minutes=30) for a, b in js)
    # centrada na leitura horária (minuto 50): janela vai de :35 a :05
    assert all(a.minute == 35 for a, _ in js)


def test_estacao_com_hora_faltando_nao_conta():
    # só 2 estações completas + uma que perde a hora 4: com min 3 nenhuma janela cobre a hora 4
    lei = leituras_horarias(8, sem_hora={2: {4}})
    js = dvr.janelas_secas(CAM, lei, 5.0, T0, T0 + timedelta(hours=8), min_estacoes=3, max_janelas=10)
    assert js
    h4 = (T0 + timedelta(hours=4), T0 + timedelta(hours=5))
    for a, b in js:  # nenhuma janela (com folga) toca a hora sem leitura
        assert b + timedelta(minutes=60) <= h4[0] or a - timedelta(minutes=60) >= h4[1]
    # com min 2 as outras duas estações bastam e a hora 4 volta a valer
    js2 = dvr.janelas_secas(CAM, lei, 5.0, T0, T0 + timedelta(hours=8), min_estacoes=2, max_janelas=10)
    assert len(js2) >= len(js)


def test_chuva_de_estacao_perto_barra_mesmo_sem_cobertura_completa():
    lei = leituras_horarias(8, chuva_10min={2: set(range(18, 24))})
    js = dvr.janelas_secas(CAM, lei, 5.0, T0, T0 + timedelta(hours=8), max_janelas=10)
    assert js
    ini, fim_ = T0 + timedelta(hours=3), T0 + timedelta(hours=4)
    for a, b in js:
        assert b + timedelta(minutes=60) <= ini or a - timedelta(minutes=60) >= fim_


def test_trecho_longo_seco_espalha_janelas_com_3h_de_distancia_e_os_dois_periodos():
    js = dvr.janelas_secas(CAM, leituras_horarias(48), 5.0, T0, T0 + timedelta(hours=48), max_janelas=10)
    assert len(js) >= 6
    inicios = sorted(a for a, _ in js)
    assert all(y - x >= timedelta(hours=3) for x, y in zip(inicios, inicios[1:]))
    assert {dvr.periodo_local(a + (b - a) / 2) for a, b in js} == {"dia", "noite"}
    assert inicios[-1] - inicios[0] > timedelta(hours=24)  # não agrupa no começo


def test_periodo_vem_do_ponto_medio():
    # janela 18:15-18:45 local: começa de dia, mas o meio (18:30) já é noite
    ini = datetime(2026, 10, 9, 21, 15, tzinfo=timezone.utc)
    assert dvr.periodo_local(ini) == "dia"
    assert dvr.periodo_janela(ini, ini + timedelta(minutes=30)) == "noite"


def test_dia_todo_seco_rende_janelas_de_dia_e_de_noite():
    js = dvr.janelas_secas(CAM, leituras(24), 5.0, T0, T0 + timedelta(hours=24), min_estacoes=2, max_janelas=4)
    assert len(js) == 4
    periodos = {dvr.periodo_janela(a, b) for a, b in js}
    assert periodos == {"dia", "noite"}
    assert all(b - a == timedelta(minutes=30) for a, b in js)
    assert all(js[i][1] <= js[i + 1][0] for i in range(len(js) - 1))


def test_chuva_afasta_a_janela_pela_folga():
    chuva = set(range(18, 24))  # 03:00–04:00 UTC+0 depois de T0
    js = dvr.janelas_secas(CAM, leituras(8, chuva_em=chuva), 5.0, T0, T0 + timedelta(hours=8), min_estacoes=2, max_janelas=10)
    assert js
    inicio_chuva, fim_chuva = T0 + timedelta(hours=3), T0 + timedelta(hours=4)
    for a, b in js:
        assert b + timedelta(minutes=60) <= inicio_chuva or a - timedelta(minutes=60) >= fim_chuva


def test_buraco_de_dado_nao_vira_seco():
    js = dvr.janelas_secas(CAM, leituras(3, buraco_em=set(range(0, 18))), 5.0, T0, T0 + timedelta(hours=3), min_estacoes=2)
    assert js == []


def test_uma_estacao_so_nao_basta():
    assert dvr.janelas_secas(CAM, leituras(24, estacoes=1), 5.0, T0, T0 + timedelta(hours=24), min_estacoes=2) == []


def test_estacao_longe_nao_conta():
    longe = [dict(r, lat=-24.5) for r in leituras(24)]
    assert dvr.janelas_secas(CAM, longe, 5.0, T0, T0 + timedelta(hours=24), min_estacoes=2) == []
