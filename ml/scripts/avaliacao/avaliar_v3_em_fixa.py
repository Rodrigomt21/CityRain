#!/usr/bin/env python3
"""F0: o modelo v3 de produção (carro, 3 classes) aplicado às câmeras fixas.

Referência para mostrar quanto se ganha separando o domínio. O v3 não prevê
`seco` (no carro isso é do gate), então só os frames de chuva entram. O irCNN
foi usado no treino do v3: a linha dele é informativa, não é teste.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "ml" / "src"))
from cityrain_ml.data.intensidade import ler_split, preparar  # noqa: E402
from cityrain_ml.evaluation.fixa import metricas_particao  # noqa: E402

C3 = ("garoa", "moderada", "forte")


def metricas_v3_em_fixa(linhas: list[dict], probs3: np.ndarray) -> dict:
    """Calcula métricas do v3 (3 classes) nas câmeras fixas, ignorando 'seco'."""
    idx = [i for i, r in enumerate(linhas) if r["classe"] in C3]
    return metricas_particao([linhas[i] for i in idx], np.asarray(probs3)[idx], C3)


def _prever(sess, linhas, lote=32) -> np.ndarray:
    """Prediz intensidade para um lote de linhas usando modelo ONNX."""
    from PIL import Image

    meta = sess.get_modelmeta().custom_metadata_map
    h, w = int(meta["altura"]), int(meta["largura"])
    nome = sess.get_inputs()[0].name
    saidas = []
    for i in range(0, len(linhas), lote):
        x = np.stack([preparar(Image.open(RAIZ / r["caminho"]), h, w) for r in linhas[i:i + lote]])
        lg = sess.run(None, {nome: x})[0]
        e = np.exp(lg - lg.max(1, keepdims=True))
        saidas.append(e / e.sum(1, keepdims=True))
    return np.concatenate(saidas) if saidas else np.zeros((0, 3))


def main() -> None:
    """Avalia v3 em câmeras fixas por partição (test_camera, test_prospectivo, lives, ircnn)."""
    import onnxruntime as ort

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--onnx", type=Path, default=RAIZ / "backend/app/inference/modelos/intensidade.onnx")
    ap.add_argument("--splits", type=Path, default=RAIZ / "ml/data/splits/fixa_v1.csv")
    ap.add_argument("--saida", type=Path, default=RAIZ / "ml/resultados/fixa_f0_v3.json")
    args = ap.parse_args()
    sess = ort.InferenceSession(str(args.onnx), providers=["CPUExecutionProvider"])
    grupos = {"test_camera": {"test_camera"}, "test_prospectivo": {"test_prospectivo"}, "lives_treino_val": {"train", "val"}, "ircnn": {"ircnn"}}
    res = {"nota": {"ircnn": "visto no treino do v3 — não é teste"}}
    for nome, parts in grupos.items():
        linhas = [r for r in ler_split(args.splits, parts) if r["classe"] in C3]
        res[nome] = metricas_v3_em_fixa(linhas, _prever(sess, linhas)) if linhas else {"n": 0}
        print(nome, json.dumps({k: res[nome].get(k) for k in ("n", "qwk", "recall_forte")}, default=float))
    args.saida.write_text(json.dumps(res, indent=2, ensure_ascii=False, default=float))


if __name__ == "__main__":
    main()
