"""Métricas do modelo de câmera fixa (NumPy puro)."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cityrain_ml.evaluation.fixa import bootstrap_eventos, bootstrap_pareado, metricas_particao  # noqa: E402
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
    # Matriz de confusão (linhas = verdade): [[1,0,0,0], [0,1,0,0], [0,0,1,0], [0,0,1,0]]
    # ou seja, células [0,0]=1, [1,1]=1, [2,2]=1 e [3,2]=1 (o forte previsto como moderada).
    # Pesos w = (i-j)²/(n-1)² com w[3,2] = 1/9 (único erro)
    # Σw·o = 1/9
    # Somas das linhas = [1,1,1,1]; das colunas = [1,1,2,0]; e = outer(linhas, colunas)/4
    # Σw·e = (1/4)(14/9·1 + 6/9·1 + 6/9·2) = 8/9
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


# --- Achado 7: recall por lado (chuva x seco) ---
def test_recall_seco_chuva_e_acuracia_balanceada():
    linhas = [_linha("seco"), _linha("seco"), _linha("garoa"), _linha("forte"), _linha("moderada"), _linha("moderada")]
    # seco: 1 de 2 certo; chuva: 2 de 4 prevista como chuva (garoa->seco e moderada->seco erram)
    m = metricas_particao(linhas, _probs([0, 1, 0, 3, 0, 2]), C)
    assert m["recall_seco"] == 0.5
    assert m["recall_chuva"] == 0.5
    assert m["acuracia_balanceada_chuva_seco"] == 0.5


def test_recall_seco_chuva_none_quando_lado_ausente():
    m = metricas_particao([_linha("garoa"), _linha("forte")], _probs([1, 3]), C)
    assert m["recall_seco"] is None and m["acuracia_balanceada_chuva_seco"] is None
    assert m["recall_chuva"] == 1.0
    m = metricas_particao([_linha("seco")], _probs([0]), C)
    assert m["recall_chuva"] is None and m["acuracia_balanceada_chuva_seco"] is None


# --- Achado 8: bloco chuva_apenas (comparação justa com F0) ---
def test_chuva_apenas_conta_seco_previsto_como_erro():
    linhas = [_linha("seco"), _linha("garoa"), _linha("moderada"), _linha("forte"), _linha("forte")]
    m = metricas_particao(linhas, _probs([0, 1, 0, 3, 0]), C)
    ca = m["chuva_apenas"]
    assert ca["n"] == 4                                    # o seco verdadeiro fica fora
    assert ca["acuracia"] == 0.5                           # garoa e um forte certos
    # F1: garoa 1.0; moderada 0 (previsto seco); forte: tp=1, fn=1, fp=0 -> 2/3. média = (1+0+2/3)/3
    assert ca["f1_macro"] == pytest.approx((1 + 0 + 2 / 3) / 3)
    assert ca["recall_forte"] == 0.5
    assert ca["qwk"] is not None


def test_chuva_apenas_sem_chuva_verdadeira():
    m = metricas_particao([_linha("seco"), _linha("seco")], _probs([0, 1]), C)
    assert m["chuva_apenas"] == {"n": 0}


# --- Achado 15: por_periodo com qwk e recall_forte ---
def test_por_periodo_tem_qwk_e_recall_forte():
    linhas = [_linha("seco"), _linha("garoa"), _linha("forte", periodo="noite"), _linha("seco", periodo="noite")]
    m = metricas_particao(linhas, _probs([0, 1, 3, 0]), C)
    dia, noite = m["por_periodo"]["dia"], m["por_periodo"]["noite"]
    assert noite["recall_forte"] == 1.0 and noite["qwk"] == 1.0
    assert dia["recall_forte"] is None


# --- Achado 4: bootstrap pareado ---
def _par():
    linhas = [_linha("forte", ev=f"e{i}") for i in range(8)] + [_linha("seco", ev=f"e{i}") for i in range(8)]
    for i, r in enumerate(linhas):
        r["caminho"] = f"c{i}"
    a = _probs([3] * 8 + [0] * 8)                       # perfeito
    b = _probs([3] * 4 + [0] * 4 + [0] * 8)             # erra metade dos fortes
    return linhas, a, b


def test_bootstrap_pareado_mostra_a_melhor():
    linhas, a, b = _par()
    r = bootstrap_pareado(linhas, a, b, C, n=200, seed=1)
    lo, hi = r["diferenca_f1_macro"]["ic95"]
    assert r["diferenca_f1_macro"]["media"] > 0 and lo <= r["diferenca_f1_macro"]["media"] <= hi
    assert r["diferenca_recall_forte"]["media"] > 0
    assert r["n_eventos"] == 8


def test_bootstrap_pareado_modelos_iguais_da_zero():
    linhas, a, _ = _par()
    r = bootstrap_pareado(linhas, a, a.copy(), C, n=50, seed=0)
    assert r["diferenca_f1_macro"]["ic95"] == [0.0, 0.0]


def test_bootstrap_pareado_exige_alinhamento_por_caminho():
    linhas, a, b = _par()
    outras = [dict(r, caminho=r["caminho"] + "x") for r in linhas]
    with pytest.raises(ValueError, match="caminho"):
        bootstrap_pareado(linhas, a, b, C, n=5, linhas_b=outras)
    with pytest.raises(ValueError):
        bootstrap_pareado(linhas, a, b[:-1], C, n=5)
    dup = [dict(r, caminho="igual") for r in linhas]
    with pytest.raises(ValueError, match="caminho"):
        bootstrap_pareado(dup, a, b, C, n=5)
