#!/usr/bin/env python3
"""Gate v2 da Jetson (seco | chuva) com validação leave-one-session-out.

Problema do ``treinar_gate.py`` (v1): cada classe vinha de UMA sessão (04/08 = seco,
01/09 = chuva), então o modelo aprendeu "qual sessão é" e não "tem gota no vidro".
Aqui:
- cada fold segura uma sessão seca e uma de chuva (nunca vistas no treino): 2 x 3 = 6 folds;
- dado externo de para-brisa (RaindropsOnWindshield, Zenodo) entra nas DUAS classes
  (1o/2o/8o = vidro limpo, máscara vazia -> seco; D2/v2 = gotas, máscara cheia -> chuva),
  quebrando "fonte = classe";
- brilho aleatório forte (simula noite) nas duas classes.

Saída com o mesmo formato do gate em produção (1x3x384x384 ``input``, ``output`` 2 logits,
índice 1 = com_gota, opset 11).

Uso:
    python treinar_gate_v2.py cv  --init imagenet|<pesos.pth> [--sem-externo] --saida ml/resultados/gate_v2_cv_<nome>.json
    python treinar_gate_v2.py final --init ... --saida ml/resultados/gate_v2.onnx
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torchvision import models as tvm

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "ml" / "src"))
from cityrain_ml.data.intensidade import preparar  # noqa: E402
from cityrain_ml.evaluation.metricas import taxa_ordenacao  # noqa: E402

LADO = 384
FR = "ml/data/processed/imt_coleta"
ZEN = "ml/data/raw/public_datasets/raindrops_zenodo/images"
SECAS = ("0408", "0608")
CHUVAS = ("0109", "1309", "2309")


def lista_sessoes() -> dict[str, list[str]]:
    """Caminhos por sessão (rótulo vem da sessão; sempre dado real)."""
    g = list(csv.DictReader(open(RAIZ / "ml/data/splits/gate_v1.csv")))
    i = list(csv.DictReader(open(RAIZ / "ml/data/splits/intensidade_v1.csv")))
    s = {
        "0408": [r["caminho"] for r in g if r["classe"] == "seco" and r["particao"] == "train"],
        "0608": [r["caminho"] for r in g if r["classe"] == "seco" and r["particao"] == "test"],
        "0109": [r["caminho"] for r in g if r["classe"] == "chuva" and r["particao"] in ("train", "val")],
        "1309": [r["caminho"] for r in g if r["particao"] == "test_real"],
        "2309": [r["caminho"] for r in i if r["particao"] == "test_ordinal_2309"],
    }
    return s


def externo(n_seco_por_pasta: int = 150) -> dict[str, list[str]]:
    rng = random.Random(0)
    seco, chuva = [], []
    for d in ("1o", "2o", "8o"):
        fs = sorted(str(p.relative_to(RAIZ)) for p in (RAIZ / ZEN / d).glob("*.png"))
        seco += rng.sample(fs, n_seco_por_pasta)
    for d in ("D2", "v2"):
        chuva += sorted(str(p.relative_to(RAIZ)) for p in (RAIZ / ZEN / d).glob("*.png"))
    return {"ext_seco": seco, "ext_chuva": chuva}


def carregar(caminhos: list[str]) -> np.ndarray:
    """uint8 N x 384 x 384 x 3 (cache em RAM)."""
    return np.stack([np.asarray(Image.open(RAIZ / c).convert("RGB").resize((LADO, LADO), Image.BILINEAR)) for c in caminhos])


MEDIA = np.array([0.485, 0.456, 0.406], np.float32)
DESVIO = np.array([0.229, 0.224, 0.225], np.float32)


def para_tensor(u8: np.ndarray, aug: bool, rng: random.Random) -> torch.Tensor:
    x = u8.astype(np.float32) / 255.0
    if aug:
        if rng.random() < 0.5:
            x = x[:, :, ::-1, :]
        esc = rng.uniform(0.25, 1.0) if rng.random() < 0.4 else rng.uniform(0.8, 1.2)  # noite simulada
        x = np.clip(x * esc * (1 + rng.uniform(-0.1, 0.1)), 0, 1)
    x = (x - MEDIA) / DESVIO
    return torch.from_numpy(np.ascontiguousarray(x.transpose(0, 3, 1, 2)))


def modelo(init: str) -> nn.Module:
    if init == "imagenet":
        m = tvm.mobilenet_v2(weights=tvm.MobileNet_V2_Weights.IMAGENET1K_V1)
        m.classifier = nn.Sequential(nn.Dropout(0.2), nn.Linear(m.last_channel, 2))
        return m
    m = tvm.mobilenet_v2(weights=None)
    m.classifier[1] = nn.Linear(m.classifier[1].in_features, 2)
    est = torch.load(init, map_location="cpu", weights_only=False)
    m.load_state_dict({k.replace("module.", ""): v for k, v in est.items()})
    return m


@torch.no_grad()
def prever(m: nn.Module, u8: np.ndarray, disp) -> np.ndarray:
    m.eval()
    rng = random.Random(0)
    out = [torch.softmax(m(para_tensor(u8[i:i + 32], False, rng).to(disp)), 1)[:, 1].cpu().numpy() for i in range(0, len(u8), 32)]
    return np.concatenate(out)


def treinar(init, X, y, epocas, lr, disp, seed):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    m = modelo(init).to(disp)
    n = np.bincount(y, minlength=2)
    perda = nn.CrossEntropyLoss(weight=torch.tensor(n.sum() / (2 * n), dtype=torch.float32).to(disp))
    otim = torch.optim.AdamW(m.parameters(), lr=lr, weight_decay=1e-4)
    rng = random.Random(seed)
    for ep in range(epocas):
        m.train()
        idx = np.random.permutation(len(X))
        soma = 0.0
        for i in range(0, len(idx), 24):
            b = idx[i:i + 24]
            xb = para_tensor(X[b], True, rng).to(disp)
            yb = torch.from_numpy(y[b]).to(disp)
            otim.zero_grad(set_to_none=True)
            loss = perda(m(xb), yb)
            loss.backward(); otim.step()
            soma += loss.item() * len(b)
        print(f"  época {ep + 1}/{epocas} loss {soma / len(X):.4f}", flush=True)
    return m


def conjunto(sess, nomes, ext, usar_ext, teto):
    rng = random.Random(1)
    cam, y = [], []
    for nm in nomes:
        c = sess[nm]
        c = rng.sample(c, min(teto, len(c)))
        cam += c; y += [0 if nm in SECAS else 1] * len(c)
    if usar_ext:
        cam += ext["ext_seco"]; y += [0] * len(ext["ext_seco"])
        cam += ext["ext_chuva"]; y += [1] * len(ext["ext_chuva"])
    return cam, np.array(y)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("modo", choices=("cv", "final"))
    ap.add_argument("--init", required=True)
    ap.add_argument("--sem-externo", action="store_true")
    ap.add_argument("--epocas", type=int, default=3)
    ap.add_argument("--lr", type=float, default=None)
    ap.add_argument("--teto", type=int, default=300, help="máx. frames por sessão no treino")
    ap.add_argument("--saida", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    lr = a.lr or (2e-4 if a.init == "imagenet" else 1e-4)
    disp = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    sess, ext = lista_sessoes(), externo()
    usar_ext = not a.sem_externo
    # cache de imagens
    todos = sorted({c for v in list(sess.values()) + list(ext.values()) for c in v})
    print(f"[gate2] carregando {len(todos)} imagens", flush=True)
    cache = dict(zip(todos, carregar(todos)))
    get = lambda cs: np.stack([cache[c] for c in cs])

    if a.modo == "final":
        cam, y = conjunto(sess, SECAS + CHUVAS, ext, usar_ext, a.teto)
        m = treinar(a.init, get(cam), y, a.epocas, lr, disp, a.seed)
        m.cpu().eval()
        a.saida.parent.mkdir(parents=True, exist_ok=True)
        torch.onnx.export(m, torch.zeros(1, 3, LADO, LADO), str(a.saida), input_names=["input"],
                          output_names=["output"], opset_version=11, dynamic_axes=None, dynamo=False)
        torch.save(m.state_dict(), a.saida.with_suffix(".pth"))
        print("[gate2] ->", a.saida)
        return

    folds = []
    for ds in SECAS:
        for dc in CHUVAS:
            cam, y = conjunto(sess, [s for s in SECAS + CHUVAS if s not in (ds, dc)], ext, usar_ext, a.teto)
            print(f"[gate2] fold seco={ds} chuva={dc} | treino seco {int((y == 0).sum())} chuva {int((y == 1).sum())}", flush=True)
            m = treinar(a.init, get(cam), y, a.epocas, lr, disp, a.seed)
            ps = prever(m, get(sess[ds]), disp)
            pc = prever(m, get(sess[dc]), disp)
            r = {"seco_fora": ds, "chuva_fora": dc, "n_seco": len(ps), "n_chuva": len(pc),
                 "auc": float(taxa_ordenacao(pc, ps))}
            for t in (0.5, 0.3, 0.2, 0.1):
                r[f"t{t}"] = {"recall": float(np.mean(pc > t)), "falso_alarme": float(np.mean(ps > t))}
            print("  ", json.dumps(r), flush=True)
            folds.append(r)
            del m
    a.saida.parent.mkdir(parents=True, exist_ok=True)
    a.saida.write_text(json.dumps({"init": a.init, "externo": usar_ext, "epocas": a.epocas, "lr": lr, "folds": folds}, indent=1))


if __name__ == "__main__":
    main()
