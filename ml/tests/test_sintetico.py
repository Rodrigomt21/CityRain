"""Testes do gerador sintético de chuva (spec D7).

Usam uma base artificial (gradiente + blocos texturizados), sem depender de
dados em disco; o banco de formas cai nas elipses de reserva.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cityrain_ml.data.sintetico import (  # noqa: E402
    beta_extincao,
    carregar_banco_formas,
    gerar_amostra,
    hash_imagem,
)

BANCO = carregar_banco_formas(None, 50)


def _base() -> np.ndarray:
    """Cena 480x640: céu em gradiente, prédios com textura, chão e capô escuro."""
    rng = np.random.default_rng(0)
    h, w = 480, 640
    img = np.zeros((h, w, 3), np.float32)
    img[:] = np.linspace(0.45, 0.7, h)[:, None, None]
    pred = (rng.random((h // 16, w // 16)) > 0.5).astype(np.float32)
    pred = np.kron(pred, np.ones((16, 16), np.float32))
    img[120:270] = 0.3 + 0.4 * pred[120:270, :, None]
    img[270:380] = 0.35
    img[400:] = 0.04
    img += rng.normal(0, 0.01, img.shape).astype(np.float32)
    return np.clip(img * 255, 0, 255).astype(np.uint8)


def _contraste_topo(img: np.ndarray) -> float:
    """Desvio padrão da luminância na faixa acima do horizonte (prédios)."""
    return float(img[120:270].astype(np.float32).mean(axis=2).std())


def _gerar(mm: float, seed: int = 1, cfg: dict | None = None):
    return gerar_amostra(_base(), 0.6, mm, seed, cfg, BANCO)


def test_mesma_seed_mesmo_hash() -> None:
    a, b = _gerar(20.0, 7), _gerar(20.0, 7)
    assert hash_imagem(a.imagem) == hash_imagem(b.imagem)
    assert hash_imagem(_gerar(20.0, 8).imagem) != hash_imagem(a.imagem)


def test_mais_mm_h_mais_gotas_ate_o_teto() -> None:
    niveis = [0.6, 0.65, 0.7, 0.75, 0.9, 3.5, 8.0, 40.0]  # teto = 1,3x => 0,78 mm/h
    n = [_gerar(m).parametros["gotas"]["n_gotas_add"] for m in niveis]
    assert n[0] == 0
    assert all(n[i] < n[i + 1] for i in range(0, 3))  # estritamente crescente abaixo do teto
    assert n[4] == n[5] == n[6] == n[7]  # satura no teto (limpador)
    assert _gerar(40.0).parametros["gotas"]["saturou"]


def test_contraste_ao_longe_cai_monotonicamente() -> None:
    c = [_contraste_topo(_gerar(m).imagem) for m in (1.0, 5.0, 12.0, 20.0, 40.0)]
    assert all(c[i] > c[i + 1] for i in range(len(c) - 1)), c
    assert c[0] < _contraste_topo(_base()) + 1e-6


def test_beta_cresce_com_mm_h() -> None:
    b = [beta_extincao(m) for m in (0.6, 5, 20, 40)]
    assert b == sorted(b) and b[0] > 0


def test_camadas_desligadas_preservam_a_base() -> None:
    cfg = {"camadas": {n: {"ativa": False} for n in ("nevoa", "streaks", "pelicula", "gotas")}}
    r = _gerar(30.0, cfg=cfg)
    assert np.array_equal(r.imagem, _base())


def test_capo_intacto_com_todas_as_camadas() -> None:
    """Faixa inferior (capô, d~0) não recebe névoa, riscos, película nem gotas."""
    base = _base()
    r = _gerar(40.0)
    assert np.array_equal(r.imagem[420:], base[420:])


def test_camada_independente_das_outras() -> None:
    """Desligar a névoa não muda as gotas sorteadas (sub-geradores por camada)."""
    cfg = {"camadas": {"nevoa": {"ativa": False}}}
    a = _gerar(20.0, 3, cfg).parametros["gotas"]
    b = _gerar(20.0, 3).parametros["gotas"]
    assert a == b


def test_spray_ligado_levanta_erro() -> None:
    with pytest.raises(NotImplementedError):
        _gerar(20.0, cfg={"camadas": {"spray": {"ativa": True}}})


@pytest.mark.parametrize("mm", [5.0, 20.0, 40.0])
def test_sem_atalho_de_brilho(mm: float) -> None:
    """A luminância acima do capô nunca sobe mais que 8% sobre a base (cai levemente)."""
    base = _base().astype(np.float32).mean(axis=2)[:400].mean()
    out = _gerar(mm).imagem.astype(np.float32).mean(axis=2)[:400].mean()
    assert out <= base * 1.08, (out, base)


def test_formas_sao_suaves_e_maioria_eliptica() -> None:
    """Toda forma tem borda de alfa ~0 (sem recorte duro) e preenche < 0,9 do bbox."""
    from cityrain_ml.data.sintetico import _resolver_dir

    banco = carregar_banco_formas(_resolver_dir("ml/data/raw/public_datasets/raindrops_zenodo/masks"), 300)
    for f in banco:
        borda = np.concatenate([f[0], f[-1], f[:, 0], f[:, -1]])
        assert borda.max() < 0.02
        assert f.sum() / f.size < 0.9  # retângulo cheio teria ~1,0
    # elipses de reserva são geradas primeiro; máscaras reais ficam no final (<= 20%)
    assert len(banco) == 300


def test_gotas_sem_retangulos_de_borda_dura() -> None:
    """Gotas isoladas numa base lisa: nenhum componente alterado parece um retângulo."""
    from scipy import ndimage as ndi

    base = np.full((480, 640, 3), 128, np.uint8)
    cfg = {
        "calibracao": {"densidade_gotas_base_mpx": 1000.0},  # denso o bastante p/ estatística
        "camadas": {
            **{n: {"ativa": False} for n in ("nevoa", "streaks", "pelicula")},
            "gotas": {"ativa": True, "teto_saturacao": 4.0},
        },
    }
    banco = carregar_banco_formas(None, 120)
    r = gerar_amostra(base, 0.6, 40.0, 5, cfg, banco)
    dif = np.abs(r.imagem.astype(int) - 128).sum(axis=2) > 6
    rot, n = ndi.label(dif)
    assert n > 100
    for i, sl in enumerate(ndi.find_objects(rot), start=1):
        h, w = rot[sl].shape
        if h * w >= 120 and h > 3 and w > 3:
            assert (rot[sl] == i).sum() / (h * w) < 0.93


def test_pelicula_sem_saltos_de_mascara() -> None:
    """Película isolada: a diferença para a base não tem degrau duro de região."""
    cfg = {"camadas": {n: {"ativa": n == "pelicula"} for n in ("nevoa", "streaks", "gotas")}}
    base = np.full((480, 640, 3), 100, np.uint8)
    base[:, 320:] = 160  # um único degrau real na cena
    r = gerar_amostra(base, 0.6, 40.0, 3, cfg, BANCO).imagem.astype(np.int32)
    dif = np.abs(r - base.astype(np.int32)).sum(axis=2).astype(np.float32)
    dif[:, 310:331] = 0  # ignora a vizinhança do degrau legítimo da cena
    assert float(np.abs(np.diff(dif, axis=1)).max()) < 25
    assert float(np.abs(np.diff(dif, axis=0)).max()) < 25


def test_ordenacao_na_regua_do_d6() -> None:
    """Spec D7: medidos com a régua do D6, os sintéticos ficam na ordem e nas faixas reais.

    Moderada ancorada em 23/09 (gotas/MP ~280-350, Laplaciano 280-360); forte
    ancorada nos vídeos YouTube de chuva forte (contraste 0,025-0,040,
    Laplaciano 190-320) e com mais cobertura de água que a moderada.
    Usa 30 amostras por classe; salva a tabela em review/sintetico_v1.
    """
    import importlib.util
    import json

    raiz = Path(__file__).resolve().parents[2]
    script = raiz / "ml" / "scripts" / "sintetico" / "validar_regua.py"
    if not (raiz / "ml/data/manifests/manifest_imt.csv").exists():
        pytest.skip("manifest/frames reais ausentes")
    sys.path.insert(0, str(script.parent))
    spec = importlib.util.spec_from_file_location("validar_regua", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    import gerar

    cfg = gerar.carregar_config(raiz / "ml/configs/sintetico_v1.yaml")
    try:
        res = mod.medir_sinteticos(cfg, 30)
    except FileNotFoundError:
        pytest.skip("frames reais ausentes")
    destino = raiz / cfg["saida"]["review_dir"] / "regua_sinteticos.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    ks = ("base", "moderada", "forte")
    m = {k: {x: res[k][x]["media"] for x in (*mod.METRICAS, "cobertura_agua")} for k in ks}
    # moderada (âncora 23/09): faixas da calibração anterior, inalteradas
    assert 270 <= m["moderada"]["gotas_mp"] <= 360, m
    assert m["base"]["contraste_local"] > m["moderada"]["contraste_local"] > m["forte"]["contraste_local"]
    assert m["base"]["var_laplaciano"] > m["moderada"]["var_laplaciano"] > m["forte"]["var_laplaciano"]
    # Teto 390 = âncora da moderada (23/09 mede ~388 na régua). Era 360; subiu
    # quando os frames sob viaduto/garagem (escuros, borrados) saíram das bases
    # em 30/09: a base foi de ~488 para ~547 e a moderada acompanhou (razão ~0,67).
    assert 280 <= m["moderada"]["var_laplaciano"] <= 390
    # forte (âncora YouTube pico): contraste 0,025-0,040, Laplaciano 190-320; sem teto de gotas/MP
    assert 0.025 <= m["forte"]["contraste_local"] <= 0.040, m
    assert 190 <= m["forte"]["var_laplaciano"] <= 320, m
    # cobertura de água (película + gotas desenhadas): forte > moderada > base
    assert m["forte"]["cobertura_agua"] > m["moderada"]["cobertura_agua"] > m["base"]["cobertura_agua"]


def test_forte_nao_altera_a_moderada_e_so_ele_tem_gotas_grandes() -> None:
    """A rampa do forte é 0 na moderada (mesma imagem de antes) e liga as gotas grandes no forte."""
    mod = _gerar(6.0, 11)
    forte = _gerar(30.0, 11)
    assert mod.parametros["rampa_forte"] == 0.0
    assert mod.parametros["gotas"]["n_gotas_grandes"] == 0
    assert forte.parametros["rampa_forte"] == 1.0
    assert forte.parametros["gotas"]["n_gotas_grandes"] > 20
    assert forte.parametros["gotas"]["n_escorridos"] > 0
    assert forte.parametros["cobertura_agua"] > mod.parametros["cobertura_agua"]
