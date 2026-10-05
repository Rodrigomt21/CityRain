#!/usr/bin/env python3
"""Exporta um checkpoint do modelo de intensidade para ONNX (consumido pelo backend).

O pré-processamento viaja DENTRO do .onnx (metadata_props): classes, altura,
largura, média e desvio. O backend lê dali, então não há constante duplicada
para sair de sincronia com o treino — o erro clássico que o ``detector.py`` da
Jetson documenta (modelo perde precisão em silêncio).

Depois de exportar, confere a paridade PyTorch × ONNX Runtime em frames reais
pelo MESMO ``preparar`` do treino e falha se a diferença passar de 1e-4.

Uso:
    ml/.venv/bin/python ml/scripts/treino/exportar_onnx.py ml/runs/<run>/melhor.pt \
        --saida backend/app/inference/modelos/intensidade.onnx
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch
from PIL import Image

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "ml" / "src"))

from cityrain_ml.data.intensidade import DESVIO, MEDIA, ler_split, preparar  # noqa: E402
from cityrain_ml.models.fabrica import construir  # noqa: E402

ENTRADA, SAIDA = "imagem", "logits"


def exportar(ckpt: Path, destino: Path, opset: int = 17) -> dict:
    estado = torch.load(ckpt, map_location="cpu", weights_only=False)
    cfg, classes = estado["config"], estado["classes"]
    h, w = cfg["entrada"]["altura"], cfg["entrada"]["largura"]
    modelo = construir(cfg["modelo"]["arquitetura"], len(classes), pretreinado=False)
    modelo.load_state_dict(estado["estado"])
    modelo.eval()

    destino.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        modelo,
        torch.zeros(1, 3, h, w),
        str(destino),
        input_names=[ENTRADA],
        output_names=[SAIDA],
        dynamic_axes={ENTRADA: {0: "lote"}, SAIDA: {0: "lote"}},
        opset_version=opset,
        dynamo=False,
    )
    meta = {
        "classes": json.dumps(classes),
        "altura": str(h),
        "largura": str(w),
        "media": json.dumps([float(x) for x in MEDIA]),
        "desvio": json.dumps([float(x) for x in DESVIO]),
        "arquitetura": cfg["modelo"]["arquitetura"],
        "experimento": cfg["nome"],
        "checkpoint": str(ckpt.relative_to(RAIZ)) if ckpt.is_relative_to(RAIZ) else ckpt.name,
        "epoca": str(estado["epoca"]),
        "saida": "logits (aplicar softmax)",
    }
    m = onnx.load(str(destino))
    for k, v in meta.items():
        p = m.metadata_props.add()
        p.key, p.value = k, v
    onnx.checker.check_model(m)
    onnx.save(m, str(destino))
    return {"modelo": modelo, "classes": classes, "h": h, "w": w, "cfg": cfg}


def conferir_paridade(info: dict, destino: Path, n: int = 24) -> float:
    """Maior diferença absoluta de probabilidade entre PyTorch e ORT em frames reais."""
    csv = RAIZ / info["cfg"]["dados"]["splits_csv"]
    linhas = [r for r in ler_split(csv, {"test_real", "test_ircnn", "test_ordinal_youtube"})]
    passo = max(1, len(linhas) // n)
    x = np.stack([preparar(Image.open(RAIZ / r["caminho"]), info["h"], info["w"]) for r in linhas[::passo][:n]])
    with torch.no_grad():
        p_pt = torch.softmax(info["modelo"](torch.from_numpy(x)), 1).numpy()
    sess = ort.InferenceSession(str(destino), providers=["CPUExecutionProvider"])
    logits = sess.run([SAIDA], {ENTRADA: x})[0]
    e = np.exp(logits - logits.max(1, keepdims=True))
    p_ort = e / e.sum(1, keepdims=True)
    return float(np.abs(p_pt - p_ort).max())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("checkpoint", type=Path)
    ap.add_argument("--saida", type=Path, default=RAIZ / "backend/app/inference/modelos/intensidade.onnx")
    args = ap.parse_args()
    destino = args.saida.resolve()
    info = exportar(args.checkpoint.resolve(), destino)
    dif = conferir_paridade(info, destino)
    print(f"[onnx] {destino.relative_to(RAIZ)} ({destino.stat().st_size / 1e6:.1f} MB) classes={info['classes']}")
    print(f"[onnx] paridade PyTorch x ORT: max |Δp| = {dif:.2e}")
    if dif > 1e-4:
        sys.exit(f"paridade falhou: {dif:.2e} > 1e-4")


if __name__ == "__main__":
    main()
