"""Testes do script de rotulagem frame -> classe de chuva (F1.3).

Usa frames e leituras de estação sintéticos, com coordenadas e intensidades
escolhidas para exercitar cada regra do plano: raio máximo, janela centrada,
zona morta nas fronteiras e determinismo da saída. Ver docs/plano-dataset.md.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

# Mesmo padrão do test_normalizacao.py: o script vive fora de um pacote Python
# instalável, então o módulo é carregado direto do arquivo pelo caminho.
_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "rotulagem" / "gerar_manifest.py"
)
_spec = importlib.util.spec_from_file_location("gerar_manifest", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
rot = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rot
_spec.loader.exec_module(rot)


# Estação de referência e um ponto a ~100 m dela (0,001° de latitude ~= 111 m).
EST_LAT, EST_LON = -23.5500, -46.6300
PERTO_LAT, PERTO_LON = -23.5491, -46.6300
T0 = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)


def _serie(valores_por_offset: dict[int, float]) -> list[tuple[datetime, float]]:
    """Monta uma série ordenada a partir de {offset_em_minutos: incremento_mm}."""
    return sorted(
        (T0 + timedelta(minutes=off), val) for off, val in valores_por_offset.items()
    )


# --------------------------------------------------------------------------
# intensidade_na_janela
# --------------------------------------------------------------------------


def test_intensidade_e_media_sobre_o_tempo_observado() -> None:
    """3 leituras de 0,2 mm em 10 min cada => 0,6 mm em 30 min => 1,2 mm/h."""
    serie = _serie({-10: 0.2, 0: 0.2, 10: 0.2})
    mm_h, n, cobertura = rot.intensidade_na_janela(serie, T0, 15, 10)
    assert n == 3
    assert cobertura == 30
    assert mm_h == pytest.approx(1.2)


def test_intensidade_usa_cobertura_real_nao_largura_da_janela() -> None:
    """Uma leitura só na janela cobre 10 min, não os 30 min nominais."""
    serie = _serie({0: 0.2})
    mm_h, n, cobertura = rot.intensidade_na_janela(serie, T0, 15, 10)
    assert (n, cobertura) == (1, 10)
    assert mm_h == pytest.approx(1.2)


def test_janela_sem_leitura_devolve_none() -> None:
    serie = _serie({-60: 5.0, 60: 5.0})
    mm_h, n, cobertura = rot.intensidade_na_janela(serie, T0, 15, 10)
    assert (mm_h, n, cobertura) == (None, 0, 0)


def test_janela_e_fechada_nos_dois_extremos() -> None:
    """Leituras exatamente em -15 e +15 min entram na janela."""
    serie = _serie({-15: 0.2, 15: 0.2})
    _, n, _ = rot.intensidade_na_janela(serie, T0, 15, 10)
    assert n == 2


def test_leituras_zeradas_dao_intensidade_zero_nao_none() -> None:
    """Estação seca transmite 0.0; isso é informação, não ausência de dado."""
    serie = _serie({0: 0.0})
    mm_h, n, _ = rot.intensidade_na_janela(serie, T0, 15, 10)
    assert n == 1 and mm_h == 0.0


# --------------------------------------------------------------------------
# classificar
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mm_h", "esperado"),
    [
        (0.0, "seco"),
        (1.2, "garoa"),
        (2.0, "garoa"),
        (3.5, "moderada"),
        (7.0, "moderada"),
        (12.0, "forte"),
        (37.8, "forte"),
    ],
)
def test_classificar_fora_da_zona_morta(mm_h: float, esperado: str) -> None:
    classe, motivo = rot.classificar(mm_h, 2.5, 10.0, 0.15)
    assert (classe, motivo) == (esperado, "")


@pytest.mark.parametrize("mm_h", [2.125, 2.5, 2.875, 8.5, 10.0, 11.5])
def test_classificar_na_zona_morta_exclui(mm_h: float) -> None:
    """±15% de 2,5 => [2.125, 2.875]; de 10 => [8.5, 11.5]."""
    classe, motivo = rot.classificar(mm_h, 2.5, 10.0, 0.15)
    assert classe == ""
    assert motivo == rot.MOTIVO_ZONA_MORTA


def test_zona_morta_zero_mantem_fronteiras_rotuladas() -> None:
    """Com zona morta desligada, o limiar pertence à classe de baixo.

    Intervalos do plano fechados à direita: garoa 0 < i <= 2,5 · moderada
    2,5 < i <= 10 · forte > 10.
    """
    assert rot.classificar(2.5, 2.5, 10.0, 0.0)[0] == "garoa"
    assert rot.classificar(2.5001, 2.5, 10.0, 0.0)[0] == "moderada"
    assert rot.classificar(10.0, 2.5, 10.0, 0.0)[0] == "moderada"
    assert rot.classificar(10.0001, 2.5, 10.0, 0.0)[0] == "forte"


# --------------------------------------------------------------------------
# rotular_frame
# --------------------------------------------------------------------------


def _estacoes_e_series(
    extras: dict[str, tuple[float, float, dict[int, float]]] | None = None,
) -> tuple[dict[str, rot.Estacao], dict[str, list[tuple[datetime, float]]]]:
    """Monta uma estação base 'E1' mais as extras pedidas."""
    estacoes = {"E1": rot.Estacao("E1", "Base", EST_LAT, EST_LON)}
    series = {"E1": _serie({-10: 0.2, 0: 0.2, 10: 0.2})}
    for eid, (lat, lon, vals) in (extras or {}).items():
        estacoes[eid] = rot.Estacao(eid, f"Est {eid}", lat, lon)
        series[eid] = _serie(vals)
    return estacoes, series


def _rotular(frame: rot.Frame, raio_km: float = 2.0, **kwargs) -> rot.LinhaManifest:
    estacoes, series = _estacoes_e_series(kwargs.pop("extras", None))
    return rot.rotular_frame(
        frame, estacoes, series, raio_km, 15, 10, 2.5, 10.0, 0.15, **kwargs
    )


def test_frame_sem_fix_sai_com_motivo_e_sem_classe() -> None:
    frame = rot.Frame("f.jpg", "p", T0, None, None)
    linha = _rotular(frame)
    assert linha.motivo_exclusao == rot.MOTIVO_SEM_FIX
    assert linha.classe == "" and linha.mm_h is None


def test_frame_sem_timestamp_sai_com_motivo() -> None:
    frame = rot.Frame("f.jpg", "p", None, PERTO_LAT, PERTO_LON)
    linha = _rotular(frame)
    assert linha.motivo_exclusao == rot.MOTIVO_SEM_TIMESTAMP


def test_frame_fora_do_raio_sai_com_motivo() -> None:
    """Ponto a ~1,1 km da estação, com raio de 0,5 km."""
    frame = rot.Frame("f.jpg", "p", T0, -23.5400, EST_LON)
    linha = _rotular(frame, raio_km=0.5)
    assert linha.motivo_exclusao == rot.MOTIVO_FORA_DO_RAIO
    assert linha.n_estacoes_no_raio == 0


def test_frame_dentro_do_raio_e_rotulado_com_distancia_em_metros() -> None:
    frame = rot.Frame("f.jpg", "p", T0, PERTO_LAT, PERTO_LON)
    linha = _rotular(frame)
    assert linha.classe == "garoa"
    assert linha.estacao_id == "E1"
    assert linha.mm_h == pytest.approx(1.2)
    assert linha.dist_m == pytest.approx(100.0, abs=5.0)


def test_estacao_no_raio_mas_sem_leitura_na_janela() -> None:
    frame = rot.Frame("f.jpg", "p", T0 + timedelta(hours=5), PERTO_LAT, PERTO_LON)
    linha = _rotular(frame)
    assert linha.motivo_exclusao == rot.MOTIVO_SEM_LEITURA
    assert linha.n_estacoes_no_raio == 1


def test_escolhe_a_estacao_mais_proxima_entre_candidatas() -> None:
    """E2 está mais longe e reporta chuva forte; deve perder para E1, mais perto."""
    extras = {"E2": (-23.5600, EST_LON, {0: 6.0})}
    frame = rot.Frame("f.jpg", "p", T0, PERTO_LAT, PERTO_LON)
    linha = _rotular(frame, extras=extras)
    assert linha.estacao_id == "E1"
    assert linha.classe == "garoa"
    assert linha.n_estacoes_no_raio == 2


def test_cai_para_a_proxima_estacao_quando_a_mais_proxima_nao_tem_leitura() -> None:
    estacoes = {
        "E1": rot.Estacao("E1", "Perto sem dado", EST_LAT, EST_LON),
        "E2": rot.Estacao("E2", "Longe com dado", -23.5520, EST_LON),
    }
    series = {"E1": [], "E2": _serie({0: 0.2})}
    frame = rot.Frame("f.jpg", "p", T0, PERTO_LAT, PERTO_LON)
    linha = rot.rotular_frame(frame, estacoes, series, 2.0, 15, 10, 2.5, 10.0, 0.15)
    assert linha.estacao_id == "E2"
    assert linha.classe == "garoa"


def test_desempate_entre_equidistantes_e_pelo_id() -> None:
    """Duas estações à mesma distância: ganha o menor id, para ser determinístico."""
    estacoes = {
        "E9": rot.Estacao("E9", "Nove", EST_LAT, EST_LON),
        "E1": rot.Estacao("E1", "Um", EST_LAT, EST_LON),
    }
    series = {"E9": _serie({0: 0.2}), "E1": _serie({0: 0.2})}
    frame = rot.Frame("f.jpg", "p", T0, PERTO_LAT, PERTO_LON)
    linha = rot.rotular_frame(frame, estacoes, series, 2.0, 15, 10, 2.5, 10.0, 0.15)
    assert linha.estacao_id == "E1"


def test_evento_id_combina_pasta_e_dia() -> None:
    frame = rot.Frame("f.jpg", "sessao_a", T0, PERTO_LAT, PERTO_LON)
    assert frame.evento_id == "sessao_a__2026-09-01"
    assert rot.Frame("f.jpg", "sessao_a", None, None, None).evento_id == (
        "sessao_a__sem_data"
    )


# --------------------------------------------------------------------------
# parsing de timestamp
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "2026-09-01T10:00:00Z",
        "2026-09-01T10:00:00+00:00",
        "2026-09-01T07:00:00-03:00",
        "2026-09-01T10:00:00",
    ],
)
def test_parse_ts_normaliza_para_utc(texto: str) -> None:
    assert rot._parse_ts(texto) == T0


@pytest.mark.parametrize("texto", ["", "nao-e-data", "2026-13-45T99:99:99Z"])
def test_parse_ts_invalido_devolve_none(texto: str) -> None:
    assert rot._parse_ts(texto) is None


# --------------------------------------------------------------------------
# ponta a ponta: main() sobre uma árvore sintética
# --------------------------------------------------------------------------


def _montar_arvore(tmp_path: Path) -> Path:
    """Cria frames, CSV de leituras e config; devolve o caminho do config."""
    raiz = tmp_path / "processed"
    pasta = raiz / "sessao_teste"
    pasta.mkdir(parents=True)

    # Dois frames com fix perto da estação, um sem fix.
    frames = [
        ("frame_a", PERTO_LAT, PERTO_LON, True),
        ("frame_b", PERTO_LAT, PERTO_LON, True),
        ("frame_c", None, None, False),
    ]
    for nome, lat, lon, fix in frames:
        (pasta / f"{nome}.jpg").write_bytes(b"")
        (pasta / f"{nome}.json").write_text(
            json.dumps(
                {
                    "schema": 1,
                    "capturado_em_utc": T0.isoformat(),
                    "arquivo": f"{nome}.jpg",
                    "gps": {
                        "fix": fix,
                        "latitude": lat,
                        "longitude": lon,
                    },
                }
            ),
            encoding="utf-8",
        )
    # Arquivo auxiliar que não é frame: não deve virar linha do manifest.
    (pasta / "_normalizacao.json").write_text("{}", encoding="utf-8")
    # Jpg sem json par: contado no relatório, fora do manifest.
    (pasta / "frame_orfao.jpg").write_bytes(b"")

    leituras = tmp_path / "leituras.csv"
    with leituras.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            ["fonte", "estacao_id", "estacao_nome", "lat", "lon", "ts_utc",
             "acumulado_mm", "janela_min"]
        )
        for off in (-10, 0, 10):
            ts = (T0 + timedelta(minutes=off)).isoformat().replace("+00:00", "Z")
            w.writerow(["teste", "E1", "Base", EST_LAT, EST_LON, ts, 0.2, 10])

    config = {
        "raiz_frames": str(raiz),
        "leituras_csv": str(leituras),
        "saida_manifest": str(tmp_path / "out" / "manifest.csv"),
        "saida_relatorio": str(tmp_path / "out" / "relatorio.json"),
        "leitura": {"minutos_por_leitura": 10},
        "rotulagem": {
            "raio_max_km": 2.0,
            "janela_min": 15,
            "zona_morta_frac": 0.15,
            "limiares_mm_h": {"garoa_max": 2.5, "moderada_max": 10.0},
        },
        "sensibilidade_raio_km": [2.0],
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return config_path


def test_main_escreve_manifest_com_todas_as_colunas(tmp_path: Path) -> None:
    config_path = _montar_arvore(tmp_path)
    assert rot.main(["--config", str(config_path)]) == 0

    manifest = tmp_path / "out" / "manifest.csv"
    with manifest.open(encoding="utf-8", newline="") as f:
        linhas = list(csv.DictReader(f))

    assert list(linhas[0].keys()) == list(rot.COLUNAS_MANIFEST)
    # 3 frames com json; o _normalizacao.json e o jpg órfão ficam fora.
    assert len(linhas) == 3
    por_arquivo = {li["arquivo"]: li for li in linhas}
    assert por_arquivo["frame_a.jpg"]["classe"] == "garoa"
    assert por_arquivo["frame_a.jpg"]["mm_h"] == "1.2000"
    assert por_arquivo["frame_a.jpg"]["motivo_exclusao"] == ""
    assert por_arquivo["frame_c.jpg"]["classe"] == ""
    assert por_arquivo["frame_c.jpg"]["motivo_exclusao"] == rot.MOTIVO_SEM_FIX

    relatorio = json.loads((tmp_path / "out" / "relatorio.json").read_text())
    assert relatorio["rotulados"] == 2
    assert relatorio["por_classe"]["garoa"] == 2
    assert relatorio["por_motivo"][rot.MOTIVO_SEM_FIX] == 1
    assert relatorio["total_jpg_sem_json"] == 1
    assert relatorio["config_sha256"]
    assert relatorio["parametros"]["raio_max_km"] == 2.0


def test_main_e_reproduzivel_byte_a_byte(tmp_path: Path) -> None:
    """Mesmo input ⇒ mesmo manifest, exigência de aceite de F1.3."""
    config_path = _montar_arvore(tmp_path)
    manifest = tmp_path / "out" / "manifest.csv"

    rot.main(["--config", str(config_path)])
    primeiro = manifest.read_bytes()
    rot.main(["--config", str(config_path)])
    assert manifest.read_bytes() == primeiro


def test_dry_run_nao_escreve_nada(tmp_path: Path) -> None:
    config_path = _montar_arvore(tmp_path)
    assert rot.main(["--config", str(config_path), "--dry-run"]) == 0
    assert not (tmp_path / "out").exists()


def test_raio_km_da_cli_sobrescreve_o_config(tmp_path: Path) -> None:
    config_path = _montar_arvore(tmp_path)
    assert rot.main(["--config", str(config_path), "--raio-km", "0.01"]) == 0
    relatorio = json.loads((tmp_path / "out" / "relatorio.json").read_text())
    assert relatorio["parametros"]["raio_max_km"] == 0.01
    assert relatorio["rotulados"] == 0
    assert relatorio["por_motivo"][rot.MOTIVO_FORA_DO_RAIO] == 2
