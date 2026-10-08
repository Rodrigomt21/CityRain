"""Métricas do modelo de câmera fixa (NumPy puro)."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

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


def test_qwk_valor_exato():
    # y_true=[0,1,2,3], y_pred=[0,1,2,2], n_classes=4
    # Matriz de confusão: [[1,0,0,0], [0,1,0,0], [0,0,0,1], [0,0,1,0]]
    # Pesos w = (i-j)²/(n-1)² com w[3,2] = 1/9 (erro penalizado)
    # Σw·o = 1/9 (apenas elemento w[3,2]=1/9 com o[3,2]=1 contribui)
    # Colunas somam [1,1,2,0]; Σw·e = (1/4)(Σw[i,:]·sum_verdade[i]·sum_pred[:])
    #             = (1/4)(14/9 + 6/9 + 2·6/9) = 8/9
    # QWK = 1 - (1/9)/(8/9) = 1 - 1/8 = 0.875
    assert kappa_quadratico([0, 1, 2, 3], [0, 1, 2, 2], 4) == pytest.approx(0.875)


def test_metricas_particao_filtra_classe_invalida():
    # Linhas com classe "chuva" (not in C) são filtradas
    linhas = [_linha("seco"), _linha("chuva"), _linha("garoa")]
    m = metricas_particao(linhas, _probs([0, 0, 1]), C)
    assert m["n"] == 2  # Apenas "seco" e "garoa" (chuva é inválido)


def test_metricas_particao_ignora_mm_h_vazio():
    # Testa que linhas com mm_h="" ou None não quebram Spearman
    linhas = [_linha("seco", mm="0"), _linha("forte", mm=""), _linha("garoa", mm=None)]
    m = metricas_particao(linhas, _probs([0, 3, 1]), C)
    assert m["n"] == 3  # Todos contam em n
    assert m["spearman_score_mm_h"] is None  # Insuficientes para Spearman (1 válido)


def test_metricas_particao_sem_forte():
    # Partition sem nenhuma linha com classe "forte"
    linhas = [_linha("seco"), _linha("garoa"), _linha("moderada")]
    m = metricas_particao(linhas, _probs([0, 1, 2]), C)
    assert m["recall_forte"] is None


def test_bootstrap_vazio_retorna_zeros():
    # Nenhuma linha com classe válida → sem eventos
    linhas = [{"classe": "invalida", "evento_id": "e1"}]
    b = bootstrap_eventos(linhas, _probs([0]), C, n=10, seed=0)
    assert b["n_eventos"] == 0
    assert b["f1_macro"] is None
    assert b["recall_forte"] is None


def test_bootstrap_eventos_homogeneos():
    # Cada evento_id deve ter todas as linhas da mesma classe
    linhas = [_linha("forte", ev="ev1"), _linha("forte", ev="ev1"), _linha("seco", ev="ev2"), _linha("seco", ev="ev2")]
    preds = [3, 3, 0, 0]
    b = bootstrap_eventos(linhas, _probs(preds), C, n=50, seed=2)
    assert b["n_eventos"] == 2
    # Com classes homogêneas, F1 deve ser definido
    assert b["f1_macro"] is not None
    assert isinstance(b["f1_macro"]["media"], float)


def test_metricas_particao_mm_h_constante():
    # Todos os valores de mm_h iguais → Spearman retorna NaN (variância zero) → converte para None
    linhas = [_linha("seco", mm="1"), _linha("forte", mm="1"), _linha("garoa", mm="1")]
    m = metricas_particao(linhas, _probs([0, 3, 1]), C)
    assert m["n"] == 3
    assert m["spearman_score_mm_h"] is None
