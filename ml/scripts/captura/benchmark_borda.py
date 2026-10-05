#!/usr/bin/env python3
"""Benchmark de borda na Jetson: latência, FPS e memória dos modelos ONNX.

Mede, com frames REAIS da própria placa, separando pré-processamento (PIL+NumPy,
igual ao detector.py) de inferência (onnxruntime), em cada provider disponível.
Compatível com o Python 3.6 da Jetson (sem dependências além de numpy, PIL e
onnxruntime, que já estão instalados).

Uso (na Jetson):
    python3 benchmark_borda.py --frames /home/jetson/frames_backlog_20261005 \
        --modelo gate=/home/jetson/modelo_chuva/bestModel.onnx:384x384 \
        --modelo intensidade=/home/jetson/modelo_chuva/intensidade_v3_op13.onnx:288x384
"""

import argparse
import glob
import json
import os
import resource
import statistics
import time

import numpy as np
from PIL import Image

MEDIA = np.array([0.485, 0.456, 0.406], dtype=np.float32)
DESVIO = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def preparar(caminho, h, w):
    img = Image.open(caminho).convert("RGB").resize((w, h), Image.BILINEAR)
    x = (np.asarray(img, dtype=np.float32) / 255.0 - MEDIA) / DESVIO
    return np.ascontiguousarray(x.transpose(2, 0, 1))[None]


def rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0  # Linux: KB


def medir(nome, caminho, h, w, provider, frames, aquecimento):
    import onnxruntime as ort

    t0 = time.time()
    sess = ort.InferenceSession(caminho, providers=[provider])
    t_carga = time.time() - t0
    entrada = sess.get_inputs()[0].name
    for f in frames[:aquecimento]:
        sess.run(None, {entrada: preparar(f, h, w)})
    t_prep, t_inf = [], []
    for f in frames[aquecimento:]:
        a = time.time()
        x = preparar(f, h, w)
        b = time.time()
        sess.run(None, {entrada: x})
        c = time.time()
        t_prep.append((b - a) * 1000)
        t_inf.append((c - b) * 1000)
    tot = [p + i for p, i in zip(t_prep, t_inf)]
    return {
        "modelo": nome, "provider": provider.replace("ExecutionProvider", ""), "entrada": "%dx%d" % (h, w),
        "tamanho_mb": round(os.path.getsize(caminho) / 1e6, 1), "carga_s": round(t_carga, 1),
        "n": len(tot), "prep_ms_mediana": round(statistics.median(t_prep), 1),
        "inferencia_ms_mediana": round(statistics.median(t_inf), 1),
        "inferencia_ms_p95": round(sorted(t_inf)[int(0.95 * (len(t_inf) - 1))], 1),
        "total_ms_mediana": round(statistics.median(tot), 1), "fps": round(1000.0 / statistics.median(tot), 1),
        "rss_max_mb": round(rss_mb(), 0),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True)
    ap.add_argument("--modelo", action="append", required=True, help="nome=caminho:HxW")
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--aquecimento", type=int, default=10)
    ap.add_argument("--providers", default="CPUExecutionProvider,CUDAExecutionProvider")
    ap.add_argument("--saida", default="benchmark_borda.json")
    args = ap.parse_args()
    frames = sorted(glob.glob(os.path.join(args.frames, "*.jpg")))[: args.n + args.aquecimento]
    res = []
    for spec in args.modelo:
        nome, resto = spec.split("=", 1)
        caminho, dims = resto.rsplit(":", 1)
        h, w = (int(v) for v in dims.split("x"))
        for prov in args.providers.split(","):
            r = medir(nome, caminho, h, w, prov, frames, args.aquecimento)
            print(json.dumps(r, ensure_ascii=False), flush=True)
            res.append(r)
    with open(args.saida, "w") as f:
        json.dump(res, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
