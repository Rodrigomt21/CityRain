"""Métricas do modelo de câmera fixa (NumPy puro)."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cityrain_ml.evaluation.fixa import bootstrap_eventos, metricas_particao  # noqa: E402
from cityrain_ml.evaluation.metricas import acuracia_chuva_vs_seco, kappa_quadratico, matriz_confusao, recall_classe  # noqa: E402

C = ("seco", "garoa", "moderada", "forte")


def _probs(preds, k=4):
    p = np.full((len(preds), k), 0.01)
    p[np.arange(len(preds)), preds] = 0.97
    return p


def test_qwk_perfeito_e_um():
    assert kappa_quadratico([0, 1, 2, 3], [0, 1, 2, 3], 4) == 1.0


def test_qwk_pune_mais_o_erro_distante():
    perto = kappa_quadratico([0, 1, 2, 3, 3], [0, 1, 2, 3, 2], 4)
    longe = kappa_quadratico([0, 1, 2, 3, 3], [0, 1, 2, 3, 0], 4)
    assert perto > longe


def test_qwk_com_uma_classe_so_e_nan():
    assert math.isnan(kappa_quadratico([1, 1], [1, 1], 4))


def test_acuracia_chuva_vs_seco_ignora_intensidade():
    assert acuracia_chuva_vs_seco([0, 1, 3, 2], [0, 3, 1, 0]) == 0.75


def test_recall_de_classe_ausente_e_none():
    m = matriz_confusao([0, 1], [0, 1], 4)
    assert recall_classe(m, 3) is None
    assert recall_classe(m, 1) == 1.0


def _linha(classe, cam="a", periodo="dia", ev="a__1", mm="0"):
    return {"classe": classe, "camera": cam, "periodo": periodo, "evento_id": ev, "mm_h": mm}


def test_metricas_particao_tem_recortes():
    linhas = [_linha("seco"), _linha("forte", mm="20"), _linha("garoa", cam="b", periodo="noite", mm="1")]
    m = metricas_particao(linhas, _probs([0, 3, 1]), C)
    assert m["n"] == 3 and m["resumo"]["acuracia"] == 1.0
    assert m["recall_forte"] == 1.0
    assert set(m["por_camera"]) == {"a", "b"} and set(m["por_periodo"]) == {"dia", "noite"}
    assert m["spearman_score_mm_h"] > 0.9


def test_metricas_particao_vazia():
    assert metricas_particao([], np.zeros((0, 4)), C) == {"n": 0}


def test_bootstrap_reamostra_eventos():
    linhas = [_linha("forte", ev=f"e{i}") for i in range(6)] + [_linha("seco", ev=f"e{i}") for i in range(6)]
    preds = [3] * 6 + [0] * 3 + [3] * 3
    b = bootstrap_eventos(linhas, _probs(preds), C, n=200, seed=1)
    lo, hi = b["f1_macro"]["ic95"]
    assert 0 <= lo <= b["f1_macro"]["media"] <= hi <= 1
