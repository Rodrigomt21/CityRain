#!/usr/bin/env python3
"""Acrescenta os frames rotulados das câmeras fixas (lives/DVR) a um CSV de splits.

Entrada: o CSV de splits base (ex.: ``intensidade_v1.csv``) e o manifest das câmeras
fixas (``gerar_manifest.py --config ml/configs/rotulagem_coleta_fixa.yaml``).
Saída: o mesmo CSV com linhas ``origem=live``:

- ``particao=train`` para todas as câmeras menos ``--teste-camera``;
- ``particao=test_lives`` para a câmera separada (cena nunca vista no treino).

Só entram garoa/moderada/forte (``seco`` é do gate). No treino, no máximo
``--max-por-grupo`` frames por (câmera-dia, classe), igualmente espaçados no tempo:
sem isso a garoa contínua do Centro de SP (milhares de frames de um mesmo dia)
afogaria o resto. O teste não é subamostrado.

Uso:
    ml/.venv/bin/python ml/scripts/dataset/adicionar_lives.py \
        --base ml/data/splits/intensidade_v1.csv --saida ml/data/splits/intensidade_v5.csv \
        --teste-camera guaruja_enseada
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
CLASSES = ("garoa", "moderada", "forte")


def linhas_lives(manifest: Path, raiz_frames: str, teste: str, max_por_grupo: int) -> list[dict]:
    with open(manifest, newline="") as f:
        rotulados = [r for r in csv.DictReader(f) if r["classe"] in CLASSES]
    grupos: dict[tuple, list[dict]] = defaultdict(list)
    for r in rotulados:
        grupos[(r["evento_id"], r["classe"])].append(r)
    saida = []
    for (_ev, _cl), rs in sorted(grupos.items()):
        rs.sort(key=lambda r: r["ts_utc"])
        teste_grupo = rs[0]["pasta"] == teste
        if not teste_grupo and len(rs) > max_por_grupo:
            passo = len(rs) / max_por_grupo
            rs = [rs[int(i * passo)] for i in range(max_por_grupo)]
        for r in rs:
            saida.append({
                "caminho": f"{raiz_frames}/{r['pasta']}/{r['arquivo']}",
                "classe": r["classe"],
                "mm_h": r["mm_h"],
                "particao": "test_lives" if teste_grupo else "train",
                "origem": "live",
                "evento_id": r["evento_id"],
                "periodo": r.get("periodo", ""),
            })
    return saida


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--saida", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, default=RAIZ / "ml/data/manifests/manifest_coleta_fixa.csv")
    ap.add_argument("--raiz-frames", default="ml/data/raw/coleta_fixa")
    ap.add_argument("--teste-camera", required=True)
    ap.add_argument("--max-por-grupo", type=int, default=150)
    args = ap.parse_args()

    with open(args.base, newline="") as f:
        leitor = csv.DictReader(f)
        campos = list(leitor.fieldnames or [])
        base = [r for r in leitor if r["origem"] != "live"]
    novas = linhas_lives(args.manifest, args.raiz_frames, args.teste_camera, args.max_por_grupo)
    with open(args.saida, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        for r in base + novas:
            w.writerow({k: r.get(k, "") for k in campos})
    cont = Counter((r["particao"], r["classe"]) for r in novas)
    print(f"{len(novas)} frames de lives -> {args.saida}")
    for (p, c), n in sorted(cont.items()):
        print(f"  {p:11s} {c:9s} {n}")


if __name__ == "__main__":
    main()
