#!/usr/bin/env python3
"""Quantização do modelo de intensidade: INT8 estático (QDQ) e FP16, com degradação medida.

Compara cada versão contra o FP32 pela **concordância de classe** e pela maior
diferença de probabilidade, em 4 conjuntos: garoa real 13/09, amostra do irCNN
(400 por classe), ordinal 23/09 e YouTube. Atenção: o modelo final treinou com
todo o irCNN, então ali a métrica é só comparação FP32 x quantizado, não teste.

Resultado de 05/10/2026 (``ml/resultados/quantizacao_20261005.json``): INT8 PTQ
desmonta fora do domínio próprio (concordância ~0,5 no irCNN/YouTube, mesmo com
calibração mista) — esperado para MobileNetV3 sem QAT; FP16 concorda em >= 99,5%
com metade do tamanho.

Uso:
    ml/.venv/bin/python ml/scripts/treino/quantizar.py --fp32 <modelo_opset13.onnx> --saida-dir <dir>
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import pandas as pd
from onnxconverter_common import float16
from onnxruntime.quantization import CalibrationDataReader, QuantFormat, QuantType, quantize_static
from onnxruntime.quantization.shape_inference import quant_pre_process
from PIL import Image

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "ml" / "src"))

from cityrain_ml.data.intensidade import preparar  # noqa: E402

C = ["garoa", "moderada", "forte"]
H, W = 288, 384


def _probs(modelo: Path, caminhos: list[str]) -> np.ndarray:
    s = ort.InferenceSession(str(modelo), providers=["CPUExecutionProvider"])
    nome = s.get_inputs()[0].name
    out = []
    for p in caminhos:
        z = s.run(None, {nome: preparar(Image.open(RAIZ / p), H, W)[None]})[0][0].astype(np.float64)
        e = np.exp(z - z.max())
        out.append(e / e.sum())
    return np.array(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fp32", type=Path, required=True)
    ap.add_argument("--splits", type=Path, default=RAIZ / "ml/data/splits/intensidade_v1.csv")
    ap.add_argument("--saida-dir", type=Path, required=True)
    args = ap.parse_args()
    args.saida_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(args.splits)

    # calibração mista: própria real + sintético + irCNN dia/noite (o irCNN está no treino do modelo final)
    random.seed(1)
    irc = df[df.particao == "test_ircnn"]
    cal = (random.sample(df[(df.particao == "train") & (df.origem == "real")].caminho.tolist(), 80)
           + random.sample(df[(df.particao == "train") & (df.origem == "sintetico")].caminho.tolist(), 80)
           + random.sample(irc[irc.periodo == "dia"].caminho.tolist(), 80)
           + random.sample(irc[irc.periodo == "noite"].caminho.tolist(), 80))

    class Leitor(CalibrationDataReader):
        def __init__(self):
            self.it = iter(cal)

        def get_next(self):
            p = next(self.it, None)
            return None if p is None else {"input": preparar(Image.open(RAIZ / p), H, W)[None]}

    pre, int8, fp16 = (args.saida_dir / n for n in ("pre.onnx", "intensidade_int8.onnx", "intensidade_fp16.onnx"))
    quant_pre_process(str(args.fp32), str(pre))
    quantize_static(str(pre), str(int8), Leitor(), quant_format=QuantFormat.QDQ, per_channel=True,
                    activation_type=QuantType.QUInt8, weight_type=QuantType.QInt8)
    onnx.save(float16.convert_float_to_float16(onnx.load(str(args.fp32)), keep_io_types=True), str(fp16))

    ircc = irc[irc.classe.isin(C)]
    amostra = pd.concat([ircc[ircc.classe == c].sample(min(400, (ircc.classe == c).sum()), random_state=0) for c in C])
    conjuntos = {"test_real_1309": df[df.particao == "test_real"], "ircnn_amostra": amostra,
                 "ordinal_2309": df[df.particao == "test_ordinal_2309"], "youtube": df[df.particao == "test_ordinal_youtube"]}
    res = {"tamanho_mb": {n: round(os.path.getsize(p) / 1e6, 1) for n, p in (("fp32", args.fp32), ("int8", int8), ("fp16", fp16))}}
    for nome, d in conjuntos.items():
        a = _probs(args.fp32, d.caminho.tolist())
        res[nome] = {"n": int(len(d))}
        for q, p in (("int8", int8), ("fp16", fp16)):
            b = _probs(p, d.caminho.tolist())
            res[nome][q] = {"concordancia": float(np.mean(a.argmax(1) == b.argmax(1))), "dp_max": float(np.abs(a - b).max())}
        print(nome, json.dumps(res[nome]))
    (args.saida_dir / "quantizacao.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
