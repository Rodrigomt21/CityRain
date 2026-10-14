"""Testes das partes puras de ml/scripts/sessao_carro/processar_sessao.py."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "sessao_carro" / "processar_sessao.py"
_spec = importlib.util.spec_from_file_location("processar_sessao", _PATH)
assert _spec is not None and _spec.loader is not None
ps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ps)

AGORA = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)


def meta(ts="2026-10-13T18:00:00+00:00", fix=True, rmc=None, arquivo=None):
    arquivo = arquivo or "frame_20261013_150000_000.jpg"
    return {
        "capturado_em_utc": ts, "arquivo": arquivo,
        "gps": {"fix": fix, "latitude": -23.5 if fix else None,
                "longitude": -46.6 if fix else None, "hora_rmc_utc": rmc},
    }


def test_ts_do_nome_converte_local_para_utc():
    assert ps.ts_do_nome("frame_20261013_150000_000.jpg") == datetime(
        2026, 10, 13, 18, 0, tzinfo=timezone.utc)
    assert ps.ts_do_nome("lixo.jpg") is None


def test_sessao_saudavel_sem_alertas():
    v = ps.validar_sessao([meta(), meta(ts="2026-10-13T18:00:01+00:00",
                                        arquivo="frame_20261013_150001_000.jpg")], AGORA)
    assert v["pct_fix"] == 100.0
    assert v["dias_utc"] == ["2026-10-13"]
    assert not [a for a in v["alertas"] if "RELÓGIO" in a]


def test_relogio_antigo_e_futuro_e_nome_divergente():
    v = ps.validar_sessao([meta(ts="2025-01-01T00:00:00+00:00")], AGORA)
    assert any("anterior" in a for a in v["alertas"])
    assert v["nome_diverge_do_json"] == 1
    v = ps.validar_sessao([meta(ts="2026-12-01T00:00:00+00:00")], AGORA)
    assert any("futuro" in a for a in v["alertas"])


def test_relogio_vs_hora_rmc_e_salto_para_tras():
    v = ps.validar_sessao([meta(rmc="2026-10-13T18:10:00+00:00")], AGORA)
    assert v["relogio_fora_do_gps"] == 1
    v = ps.validar_sessao([meta(ts="2026-10-13T18:00:05+00:00"), meta()], AGORA)
    assert any("salto" in a for a in v["alertas"])


def test_sem_fix_e_gps_fraco():
    v = ps.validar_sessao([meta(fix=False)] * 3, AGORA)
    assert v["pct_fix"] == 0 and any("NENHUM" in a for a in v["alertas"])
    v = ps.validar_sessao([meta(), meta(fix=False), meta(fix=False)], AGORA)
    assert any("GPS fraco" in a for a in v["alertas"])


def test_dias_necessarios_inclui_virada_de_dia():
    ini = datetime(2026, 10, 13, 22, 0, tzinfo=timezone.utc)
    fim = datetime(2026, 10, 13, 23, 30, tzinfo=timezone.utc)
    assert ps.dias_necessarios(ini, fim) == ["2026-10-13", "2026-10-14"]
    assert ps.dias_necessarios(ini.replace(hour=12), ini.replace(hour=14)) == ["2026-10-13"]


def test_estacoes_perto_da_rota():
    est = {"A": ("perto", -23.55, -46.63), "B": ("longe", -30.0, -51.0)}
    assert ps.estacoes_perto_da_rota(est, [(-23.54, -46.62)]) == ["A"]


def test_pares_faltantes_respeita_cache(tmp_path: Path):
    (tmp_path / "dados_pcd_A_2026-10-13.json").write_text("[1]")
    (tmp_path / "ERRO_B_2026-10-13.txt").write_text("HTTP 202 Nenhum resultado")
    (tmp_path / "ERRO_C_2026-10-13.txt").write_text("HTTP 401 acessos")
    assert ps.pares_faltantes(["A", "B", "C", "D"], ["2026-10-13"], tmp_path) == [
        ("C", "2026-10-13"), ("D", "2026-10-13")]


def test_resumo_por_classe_e_motivo():
    linhas = [
        {"evento_id": "e1", "classe": "garoa", "motivo_exclusao": ""},
        {"evento_id": "e1", "classe": "seco", "motivo_exclusao": ""},
        {"evento_id": "e1", "classe": "", "motivo_exclusao": "sem_gps_fix"},
    ]
    ev = ps.resumir_manifest(linhas)
    assert ev["e1"]["classes"]["garoa"] == 1 and ev["e1"]["motivos"]["sem_gps_fix"] == 1
    txt = ps.formatar_resumo(ev)
    assert "2 rotulados" in txt and "sem_gps_fix" in txt and "garoa=1" in txt
