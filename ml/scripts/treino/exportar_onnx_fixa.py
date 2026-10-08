#!/usr/bin/env python3
"""Exporta um checkpoint do modelo de câmera fixa para ONNX (consumido pelo backend).

Igual ao ``exportar_onnx.py`` (modelo de produção v3), com duas diferenças: a
entrada tem 3 ou 6 canais (frame + referência seca da mesma câmera/período) e,
no caso de 6 canais, as imagens de referência são copiadas para o backend em
``<referencias>/fixa-<camera>/<periodo>.jpg``.

O pré-processamento viaja DENTRO do .onnx (metadata_props). Depois de exportar,
confere a paridade PyTorch × ONNX Runtime e falha se passar de 1e-4.

Uso:
    ml/.venv/bin/python ml/scripts/treino/exportar_onnx_fixa.py ml/runs/<run>/melhor.pt \
        --saida backend/app/inference/modelos/intensidade_fixa.onnx \
        --referencias backend/app/inference/referencias
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "ml" / "src"))

from cityrain_ml.data.fixa import CLASSES_FIXA, DatasetFixa  # noqa: E402
from cityrain_ml.data.intensidade import DESVIO, MEDIA, ler_split  # noqa: E402
from cityrain_ml.models.fabrica import construir  # noqa: E402

ENTRADA, SAIDA = "imagem", "logits"
# Ordem de preferência das partições usadas na conferência de paridade.
PARTICOES_PARIDADE = ("test_camera", "ircnn", "val", "train")


def exportar_fixa(ckpt: Path, destino: Path, opset: int = 17) -> dict:
    """Exporta o checkpoint para ONNX com metadata e devolve o contexto da conferência."""
    estado = torch.load(ckpt, map_location="cpu", weights_only=False)
    cfg, classes = estado["config"], estado["classes"]
    canais = int(estado.get("canais_entrada", 3))
    h, w = cfg["entrada"]["altura"], cfg["entrada"]["largura"]
    modelo = construir(cfg["modelo"]["arquitetura"], len(classes), pretreinado=False, canais_entrada=canais)
    modelo.load_state_dict(estado["estado"])
    modelo.eval()

    destino.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        modelo,
        torch.zeros(1, canais, h, w),
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
        "canais_entrada": str(canais),
        "referencia": "mesma_camera_mesmo_periodo" if canais == 6 else "nenhuma",
    }
    m = onnx.load(str(destino))
    for k, v in meta.items():
        p = m.metadata_props.add()
        p.key, p.value = k, v
    onnx.checker.check_model(m)
    onnx.save(m, str(destino))
    return {"modelo": modelo, "classes": classes, "h": h, "w": w, "cfg": cfg, "canais": canais}


def conferir_paridade_fixa(info: dict, destino: Path, raiz: Path, n: int = 16) -> float:
    """Maior |Δp| entre PyTorch e ORT em até ``n`` amostras reais, pelo mesmo ``DatasetFixa`` do treino."""
    canais = info["canais"]
    linhas = ler_split(raiz / info["cfg"]["dados"]["splits_csv"])
    escolhidas: list[dict] = []
    for part in PARTICOES_PARIDADE:
        escolhidas += [
            r for r in linhas
            if r["particao"] == part and r["classe"] in CLASSES_FIXA and (canais != 6 or r.get("referencia"))
        ]
        if len(escolhidas) >= n:
            break
    escolhidas = escolhidas[:n]
    if not escolhidas:
        raise ValueError("nenhuma amostra disponível para conferir a paridade")
    ds = DatasetFixa(escolhidas, raiz, CLASSES_FIXA, info["h"], info["w"], com_referencia=canais == 6)
    x = np.stack([ds[i][0] for i in range(len(ds))])
    with torch.no_grad():
        p_pt = torch.softmax(info["modelo"](torch.from_numpy(x)), 1).numpy()
    sess = ort.InferenceSession(str(destino), providers=["CPUExecutionProvider"])
    logits = sess.run([SAIDA], {ENTRADA: x})[0]
    e = np.exp(logits - logits.max(1, keepdims=True))
    p_ort = e / e.sum(1, keepdims=True)
    return float(np.abs(p_pt - p_ort).max())


def copiar_referencias(splits_csv: Path, raiz: Path, dir_refs: Path) -> list[Path]:
    """Copia as referências secas das lives para ``<dir_refs>/fixa-<camera>/<periodo>.jpg``."""
    copiadas: list[Path] = []
    for r in ler_split(splits_csv, {"referencia"}):
        if r["origem"] != "live":
            continue
        alvo = dir_refs / f"fixa-{r['camera']}" / f"{r['periodo']}.jpg"
        alvo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(raiz / r["caminho"], alvo)
        copiadas.append(alvo)
    return copiadas


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("checkpoint", type=Path)
    ap.add_argument("--saida", type=Path, default=RAIZ / "backend/app/inference/modelos/intensidade_fixa.onnx")
    ap.add_argument("--referencias", type=Path, default=RAIZ / "backend/app/inference/referencias")
    args = ap.parse_args()
    destino = args.saida.resolve()
    info = exportar_fixa(args.checkpoint.resolve(), destino)
    dif = conferir_paridade_fixa(info, destino, RAIZ)
    tam = destino.stat().st_size / 1e6
    print(f"[onnx] {destino} ({tam:.1f} MB) classes={info['classes']} canais={info['canais']}")
    print(f"[onnx] paridade PyTorch x ORT: max |Δp| = {dif:.2e}")
    if dif > 1e-4:
        sys.exit(f"paridade falhou: {dif:.2e} > 1e-4")
    if info["canais"] == 6:
        refs = copiar_referencias(RAIZ / info["cfg"]["dados"]["splits_csv"], RAIZ, args.referencias.resolve())
        print(f"[onnx] {len(refs)} referências copiadas para {args.referencias}")


if __name__ == "__main__":
    main()
