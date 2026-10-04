"""Testes das métricas e do dataset do treino de intensidade (sem PyTorch)."""

from __future__ import annotations

import random
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cityrain_ml.data.intensidade import DatasetIntensidade, aumentar  # noqa: E402
from cityrain_ml.evaluation.metricas import (  # noqa: E402
    CLASSES,
    f1_macro,
    matriz_confusao,
    resumo_classificacao,
    score_intensidade,
    spearman,
    taxa_ordenacao,
)


def test_matriz_confusao_linhas_verdade():
    m = matriz_confusao([0, 0, 1, 2], [0, 1, 1, 0], 3)
    assert m.tolist() == [[1, 1, 0], [0, 1, 0], [1, 0, 0]]


def test_f1_macro_ignora_classe_ausente_na_verdade():
    # só garoa na verdade (caso do test_real): acertar tudo dá 1, não 1/3
    m = matriz_confusao([0, 0, 0], [0, 0, 0], 3)
    assert f1_macro(m) == pytest.approx(1.0)


def test_f1_macro_conta_predicao_errada_para_classe_ausente():
    m = matriz_confusao([0, 0, 0, 0], [0, 0, 2, 2], 3)
    assert f1_macro(m) == pytest.approx(2 * 2 / (2 + 4))


def test_score_intensidade_classe_esperada():
    assert score_intensidade(np.array([[1, 0, 0], [0, 0, 1], [0.5, 0, 0.5]])).tolist() == [0, 2, 1]


def test_taxa_ordenacao_extremos_e_empate():
    assert taxa_ordenacao([2, 3], [0, 1]) == 1.0
    assert taxa_ordenacao([0, 1], [2, 3]) == 0.0
    assert taxa_ordenacao([1, 1], [1, 1]) == 0.5


def test_taxa_ordenacao_bate_com_forca_bruta():
    rng = np.random.default_rng(0)
    a, b = rng.integers(0, 5, 40).astype(float), rng.integers(0, 5, 30).astype(float)
    bruta = np.mean([(x > y) + 0.5 * (x == y) for x in a for y in b])
    assert taxa_ordenacao(a, b) == pytest.approx(bruta)


def test_spearman_monotono():
    assert spearman([1, 2, 3, 4], [10, 20, 25, 100]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)


def test_resumo_classificacao_campos():
    r = resumo_classificacao([0, 1, 2], np.eye(3))
    assert r["f1_macro"] == 1.0 and r["acuracia"] == 1.0 and set(r["f1_por_classe"]) == set(CLASSES)


def _imagem(tmp_path: Path, nome: str) -> str:
    Image.fromarray((np.random.default_rng(1).random((48, 64, 3)) * 255).astype(np.uint8)).save(tmp_path / nome)
    return nome


def test_dataset_formato_e_rotulo(tmp_path):
    linhas = [
        {"caminho": _imagem(tmp_path, "a.jpg"), "classe": "forte"},
        {"caminho": _imagem(tmp_path, "b.jpg"), "classe": ""},  # ordinal, sem classe
    ]
    ds = DatasetIntensidade(linhas, tmp_path, CLASSES, 24, 32)
    x, y = ds[0]
    assert x.shape == (3, 24, 32) and x.dtype == np.float32 and y == 2
    assert ds[1][1] == -1


def test_aumentacao_deterministica_por_seed(tmp_path):
    img = Image.open(tmp_path / _imagem(tmp_path, "c.jpg"))
    cfg = {"recorte_escala_min": 0.8, "brilho_contraste": 0.2, "jpeg_qualidade_min": 60}
    a = np.asarray(aumentar(img, random.Random(7), cfg))
    b = np.asarray(aumentar(img, random.Random(7), cfg))
    assert np.array_equal(a, b)


def test_subamostragem_por_classe_preserva_classe_rara():
    pytest.importorskip("torch")
    from cityrain_ml.training.intensidade import subamostrar_por_evento

    linhas = [{"evento_id": "e1", "classe": "forte", "caminho": f"x/t{i}.jpg"} for i in range(1000)]
    linhas += [{"evento_id": "e1", "classe": "garoa", "caminho": f"x/t{1000 + i}.jpg"} for i in range(30)]
    so_evento = subamostrar_por_evento(linhas, 100)
    por_classe = subamostrar_por_evento(linhas, 100, por_classe=True)
    assert len(so_evento) == 100 and sum(r["classe"] == "garoa" for r in so_evento) <= 4
    assert sum(r["classe"] == "garoa" for r in por_classe) == 30
    assert sum(r["classe"] == "forte" for r in por_classe) == 100
