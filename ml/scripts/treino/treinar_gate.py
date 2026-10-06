#!/usr/bin/env python3
"""Ajuste fino do gate binário da Jetson (com_gota | sem_gota) com os dados da nossa câmera.

O gate original (``bestModel.pth``, MobileNetV2 384x384) foi treinado em outro
conjunto e, nas nossas sessões, deixa passar só 1–36% dos frames com chuva real
(AUC 0,83 contra seco 04/08+06/08, 05/10/2026). Este script parte DOS PESOS DELE
(mantém o que ele sabe de gota) e ajusta com ``ml/data/splits/gate_v1.csv``:

- treino: seco 04/08 (dia, todos os frames) + chuva 01/09 (garoa real, stride 2 s);
- teste: seco 06/08 (noite, nunca visto), chuva 13/09 (test_real) e 23/09 (ordinal).

Sai no MESMO formato do gate em produção (entrada fixa 1x3x384x384 ``input``,
saída ``output`` com 2 logits, índice 1 = com_gota, opset 11 — onnxruntime 1.10 da
Jetson), então troca na placa sem mexer no ``detector.py``.

Uso:
    ml/.venv/bin/python ml/scripts/treino/treinar_gate.py --pesos <bestModel.pth> --saida <gate.onnx>
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import models as tvm

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "ml" / "src"))

from cityrain_ml.data.intensidade import DatasetIntensidade, ler_split  # noqa: E402
from cityrain_ml.evaluation.metricas import taxa_ordenacao  # noqa: E402

CLASSES = ("seco", "chuva")  # índice 1 = com_gota, igual ao detector.py
LADO = 384


def modelo_gate(pesos: Path | None) -> nn.Module:
    m = tvm.mobilenet_v2(weights=None)
    m.classifier[1] = nn.Linear(m.classifier[1].in_features, 2)
    if pesos:
        estado = torch.load(pesos, map_location="cpu", weights_only=False)
        estado = estado.get("state_dict", estado) if isinstance(estado, dict) else estado.state_dict()
        m.load_state_dict({k.replace("module.", ""): v for k, v in estado.items()})
    return m


@torch.no_grad()
def p_chuva(m: nn.Module, linhas: list[dict], disp) -> np.ndarray:
    m.eval()
    ds = DatasetIntensidade(linhas, RAIZ, CLASSES, LADO, LADO)
    out = [torch.softmax(m(x.to(disp)), 1)[:, 1].cpu().numpy() for x, _ in DataLoader(ds, batch_size=32, num_workers=4)]
    return np.concatenate(out) if out else np.zeros(0)


def avaliar(m: nn.Module, csv_gate: Path, csv_int: Path, disp) -> dict:
    g = ler_split(csv_gate)
    seco_noite = [r for r in g if r["particao"] == "test" and r["classe"] == "seco"]
    chuva_1309 = [r for r in g if r["particao"] == "test_real"]
    chuva_2309 = [{**r, "classe": "chuva"} for r in ler_split(csv_int, {"test_ordinal_2309"})]
    ps, p13, p23 = p_chuva(m, seco_noite, disp), p_chuva(m, chuva_1309, disp), p_chuva(m, chuva_2309, disp)
    chuva = np.concatenate([p13, p23])
    res = {"auc_chuva_vs_seco_noite": taxa_ordenacao(chuva, ps)}
    for t in (0.5, 0.2):
        res[f"limiar_{t}"] = {
            "recall_13_09": float(np.mean(p13 > t)),
            "recall_23_09": float(np.mean(p23 > t)),
            "falso_alarme_seco_noite": float(np.mean(ps > t)),
        }
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pesos", type=Path, required=True, help="bestModel.pth do gate atual")
    ap.add_argument("--saida", type=Path, required=True, help=".onnx do gate ajustado")
    ap.add_argument("--epocas", type=int, default=5)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    disp = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    csv_gate, csv_int = RAIZ / "ml/data/splits/gate_v1.csv", RAIZ / "ml/data/splits/intensidade_v1.csv"

    m = modelo_gate(args.pesos).to(disp)
    antes = avaliar(m, csv_gate, csv_int, disp)
    print("[gate] ANTES:", json.dumps(antes, ensure_ascii=False))

    treino = [r for r in ler_split(csv_gate, {"train"})]
    aug = {"flip_horizontal": True, "recorte_escala_min": 0.85, "brilho_contraste": 0.25, "jpeg_qualidade_min": 60}
    ds = DatasetIntensidade(treino, RAIZ, CLASSES, LADO, LADO, aug, args.seed)
    n = np.bincount([ds.rotulo(i) for i in range(len(ds))], minlength=2)
    perda = nn.CrossEntropyLoss(weight=torch.tensor(n.sum() / (2 * n), dtype=torch.float32).to(disp))
    otim = torch.optim.AdamW(m.parameters(), lr=args.lr, weight_decay=1e-4)
    print(f"[gate] treino: seco {n[0]}, chuva {n[1]} | {disp}")
    for ep in range(args.epocas):
        ds.epoca = ep
        m.train()
        soma = 0.0
        for x, y in DataLoader(ds, batch_size=24, shuffle=True, num_workers=4):
            x, y = x.to(disp), y.to(disp)
            otim.zero_grad(set_to_none=True)
            loss = perda(m(x), y)
            loss.backward()
            otim.step()
            soma += loss.item() * len(y)
        print(f"[gate] época {ep + 1}/{args.epocas} loss {soma / len(ds):.4f}", flush=True)

    depois = avaliar(m, csv_gate, csv_int, disp)
    print("[gate] DEPOIS:", json.dumps(depois, ensure_ascii=False))
    m.cpu().eval()
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(m, torch.zeros(1, 3, LADO, LADO), str(args.saida), input_names=["input"],
                      output_names=["output"], opset_version=11, dynamic_axes=None, dynamo=False)
    torch.save(m.state_dict(), args.saida.with_suffix(".pth"))
    (args.saida.with_suffix(".json")).write_text(json.dumps({"antes": antes, "depois": depois}, indent=2, ensure_ascii=False))
    print(f"[gate] -> {args.saida}")


if __name__ == "__main__":
    main()
