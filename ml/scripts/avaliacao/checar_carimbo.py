#!/usr/bin/env python3
"""Checa se o modelo usa o carimbo de data/hora do irCNN como atalho de domínio.

Borra a faixa do topo (carimbo) e a do rodapé ("IPC") de 900 frames do irCNN
(300 por classe) e compara as predições do ONNX de produção com e sem o carimbo.
05/10/2026: concordância 0,968; F1 0,868 -> 0,856 (o modelo final treinou no
irCNN: comparação só relativa) — o carimbo não é atalho relevante.

Uso: ml/.venv/bin/python ml/scripts/avaliacao/checar_carimbo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
import pandas as pd
from PIL import Image, ImageFilter

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "ml" / "src"))

from cityrain_ml.data.intensidade import preparar  # noqa: E402
from cityrain_ml.evaluation.metricas import CLASSES, resumo_classificacao  # noqa: E402


def borrar_faixas(img: Image.Image, topo: float = 0.08, rodape: float = 0.07) -> Image.Image:
    w, h = img.size
    im = img.copy()
    for y0, y1 in ((0, int(h * topo)), (int(h * (1 - rodape)), h)):
        im.paste(im.crop((0, y0, w, y1)).filter(ImageFilter.GaussianBlur(25)), (0, y0))
    return im


def main() -> None:
    s = ort.InferenceSession(str(RAIZ / "backend/app/inference/modelos/intensidade.onnx"), providers=["CPUExecutionProvider"])
    nome = s.get_inputs()[0].name
    df = pd.read_csv(RAIZ / "ml/data/splits/intensidade_v1.csv")
    ir = df[(df.particao == "test_ircnn") & df.classe.isin(CLASSES)]
    am = pd.concat([ir[ir.classe == c].sample(min(300, (ir.classe == c).sum()), random_state=1) for c in CLASSES])

    def p(img):
        z = s.run(None, {nome: preparar(img, 288, 384)[None]})[0][0]
        e = np.exp(z - z.max())
        return e / e.sum()

    a, b = [], []
    for c in am.caminho:
        img = Image.open(RAIZ / c).convert("RGB")
        a.append(p(img))
        b.append(p(borrar_faixas(img)))
    a, b = np.array(a), np.array(b)
    y = [CLASSES.index(c) for c in am.classe]
    print(f"concordância com/sem carimbo: {np.mean(a.argmax(1) == b.argmax(1)):.3f}")
    print(f"F1 com {resumo_classificacao(y, a)['f1_macro']:.3f}  sem {resumo_classificacao(y, b)['f1_macro']:.3f}")


if __name__ == "__main__":
    main()
