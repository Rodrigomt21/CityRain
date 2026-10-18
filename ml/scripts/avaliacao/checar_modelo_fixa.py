#!/usr/bin/env python3
"""Confere um .onnx de câmera fixa ANTES de trocar o de produção (1 comando, ~1 min).

1. Contrato: metadata_props que o backend lê (classes, altura, largura, media, desvio, canais_entrada,
   referencia); classes na ordem seco, garoa, moderada, forte.
2. Carrega pelo próprio InferenceService do backend (o mesmo código que roda no Railway).
3. Compara com o modelo atual (backend/app/inference/modelos/intensidade_fixa.onnx) em:
   - test_camera de fixa_v1.csv (Balneário Camboriú, rótulo de pluviômetro): acerto e F1 macro;
   - fotos de um dia de sol (padrão: frames de 18/10/2026 do coletor), onde o certo é "seco".

Uso (da raiz do repositório):
    backend/.venv/bin/python ml/scripts/avaliacao/checar_modelo_fixa.py caminho/novo.onnx
    backend/.venv/bin/python ml/scripts/avaliacao/checar_modelo_fixa.py novo.onnx --sol "ml/data/raw/coleta_fixa/*/frame_20261018_*.jpg"

Passou? Copiar para backend/app/inference/modelos/intensidade_fixa.onnx, commit em branch e PR (GUIA-TREINO-EQUIPE §6).
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import glob
import json
import os
import sys
from collections import Counter
from pathlib import Path

import onnx

RAIZ = Path(__file__).resolve().parents[3]
ATUAL = RAIZ / "backend/app/inference/modelos/intensidade_fixa.onnx"
CHAVES = ("classes", "altura", "largura", "media", "desvio", "canais_entrada", "referencia")
CLASSES = ["seco", "garoa", "moderada", "forte"]
ROTULO_BACKEND = {"moderado": "moderada"}  # o backend grava "moderado"


def contrato(caminho: Path) -> bool:
    meta = {p.key: p.value for p in onnx.load(str(caminho)).metadata_props}
    faltam = [k for k in CHAVES if k not in meta]
    ok = not faltam and json.loads(meta.get("classes", "[]")) == CLASSES
    print(f"[contrato] {caminho.name}: {'ok' if ok else 'FALHOU'}"
          + (f" | faltam {faltam}" if faltam else "") + f" | classes {meta.get('classes')} | {meta.get('experimento', '?')}")
    if meta.get("referencia", "nenhuma") != "nenhuma":
        print("  [aviso] modelo com imagem de referência (F3): precisa de backend/app/inference/referencias/<device>/")
    return ok


def servico(caminho: Path):
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")  # só para importar o backend
    sys.path.insert(0, str(RAIZ / "backend"))
    from app.services.inference_service import InferenceService
    s = InferenceService(padrao=caminho, config_attr="inference_model_fixa_path")
    s.carregar(caminho)
    if not s.disponivel:
        sys.exit(f"[FALHA] o backend não carregou {caminho}")
    return s


def prever(s, caminhos: list[str]) -> list[str]:
    async def todos():
        return [await s.classificar((RAIZ / c).read_bytes() if not os.path.isabs(c) else Path(c).read_bytes()) for c in caminhos]
    return [ROTULO_BACKEND.get(r.label, r.label) or "sem_classe" for r in asyncio.run(todos())]


def f1_macro(y: list[str], p: list[str]) -> float:
    f1s = []
    for c in CLASSES:
        tp = sum(a == c and b == c for a, b in zip(y, p))
        fp = sum(a != c and b == c for a, b in zip(y, p))
        fn = sum(a == c and b != c for a, b in zip(y, p))
        if tp + fp + fn:
            f1s.append(2 * tp / (2 * tp + fp + fn))
    return sum(f1s) / len(f1s) if f1s else 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("novo", type=Path)
    ap.add_argument("--sol", default=str(RAIZ / "ml/data/raw/coleta_fixa/*/frame_20261018_*.jpg"),
                    help="glob de fotos de dia de sol (certo = seco)")
    a = ap.parse_args()
    if not contrato(a.novo):
        sys.exit(1)
    contrato(ATUAL)
    teste = [r for r in csv.DictReader(open(RAIZ / "ml/data/splits/fixa_v1.csv")) if r["particao"] == "test_camera"]
    sol = sorted(glob.glob(a.sol))
    for nome, caminho in (("atual", ATUAL), ("novo", a.novo)):
        s = servico(caminho)
        p = prever(s, [r["caminho"] for r in teste])
        y = [r["classe"] for r in teste]
        q = prever(s, sol)
        print(f"[{nome}] test_camera BC (n={len(y)}): acerto {sum(map(str.__eq__, p, y)) / len(y):.3f}  "
              f"F1 macro {f1_macro(y, p):.3f}  | "
              f"dia de sol (n={len(q)}): seco {q.count('seco')}/{len(q)} {dict(Counter(q))}")


if __name__ == "__main__":
    main()
