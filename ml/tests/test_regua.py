"""Testes da régua de chuva (D6) com imagens sintéticas pequenas."""

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "sintetico"))
import medir_regua as m  # noqa: E402


def _fundo(h: int = 300, w: int = 640, nivel: int = 120) -> np.ndarray:
    rng = np.random.default_rng(0)
    base = np.full((h, w), nivel, np.float32) + rng.normal(0, 1.0, (h, w))
    return np.clip(base, 0, 255).astype(np.uint8)


def _com_circulos(n: int, raio: int = 3) -> np.ndarray:
    img = _fundo()
    rng = np.random.default_rng(1)
    pts = []
    while len(pts) < n:
        x, y = int(rng.integers(30, 610)), int(rng.integers(30, 270))
        if all((x - a) ** 2 + (y - b) ** 2 > 60**2 for a, b in pts):
            pts.append((x, y))
    for x, y in pts:
        cv2.circle(img, (x, y), raio, 190, -1)
    return cv2.GaussianBlur(img, (0, 0), 0.8)


def test_detector_conta_circulos() -> None:
    for n in (5, 12):
        achados = m.detectar_gotas(_com_circulos(n))
        assert 0.7 * n <= len(achados) <= 1.5 * n


def test_detector_nao_acha_nada_em_fundo_liso() -> None:
    assert len(m.detectar_gotas(_fundo())) <= 2


def test_detector_rejeita_linhas() -> None:
    img = _fundo()
    cv2.line(img, (20, 150), (620, 150), 200, 3)  # fio/poste: borda, não blob
    assert len(m.detectar_gotas(img)) <= 3


def test_raio_estimado_cresce_com_raio_real() -> None:
    r_peq = m.detectar_gotas(_com_circulos(6, raio=2))[:, 2].mean()
    r_gde = m.detectar_gotas(_com_circulos(6, raio=4))[:, 2].mean()
    assert r_gde > r_peq


def test_contraste_cai_com_nevoa() -> None:
    rng = np.random.default_rng(2)
    cena = rng.integers(40, 160, (300, 640)).astype(np.float32)
    cena = cv2.GaussianBlur(cena, (0, 0), 2)
    nevoa = 0.4 * cena + 0.6 * 200
    c0, _ = m.contraste_horizonte(cena.astype(np.uint8))
    c1, _ = m.contraste_horizonte(nevoa.astype(np.uint8))
    assert c1 < c0


def test_contraste_ignora_ceu_saturado() -> None:
    img = np.full((300, 640), 250, np.uint8)
    rms, _ = m.contraste_horizonte(img)
    assert np.isnan(rms)


def test_var_laplaciano_cai_com_desfoque() -> None:
    img = _com_circulos(10)
    assert m.var_laplaciano(cv2.GaussianBlur(img, (0, 0), 3)) < m.var_laplaciano(img)


def test_normalizar_largura_e_roi() -> None:
    img = np.zeros((480, 360, 3), np.uint8)
    n = m.normalizar(img, 640)
    assert n.shape[1] == 640
    assert m.recortar_roi(n).shape[0] == int(n.shape[0] * (1 - m.PARAMS["excluir_base_frac"]))


def test_medir_imagem_deterministico() -> None:
    bgr = cv2.cvtColor(_com_circulos(8), cv2.COLOR_GRAY2BGR)
    assert m.medir_imagem(bgr) == m.medir_imagem(bgr.copy())
