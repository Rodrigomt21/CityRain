#!/usr/bin/env python3
"""Painéis de revisão visual por (câmera, classe) para o dataset da câmera fixa (CF3.1).

A revisão NÃO muda rótulo: o rótulo vem do pluviômetro. Ela só marca frames a
excluir por defeito da imagem (câmera tampada, congelada, tela de offline,
transmissão trocada). Marque `excluir=1` e um `motivo` no revisao.csv.

Uso:
    ml/.venv/bin/python ml/scripts/dataset/paineis_revisao_fixa.py \\
        --manifest ml/data/manifests/manifest_coleta_fixa.csv \\
        --manifest ml/data/manifests/manifest_coleta_fixa_5km.csv \\
        --raiz-frames ml/data/raw/coleta_fixa --saida ml/data/review/camera_fixa
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parents[3]
MARCAS_EXCLUIR = {"1", "sim", "s", "x"}
COLUNAS_REVISAO = ["pasta", "arquivo", "camera", "classe", "manifest", "excluir", "motivo"]


CLASSES_5KM = {"moderada", "forte"}


def classes_do_manifest(nome: str) -> set[str] | None:
    """Classes a revisar num manifest: o de 5 km só rotula moderada/forte; os demais, todas (None)."""
    return CLASSES_5KM if "_5km" in nome else None


def amostrar_por_grupo(linhas: list[dict], n: int, seed: int,
                       classes: set[str] | None = None) -> dict[tuple[str, str], list[dict]]:
    """Até `n` linhas por (câmera, classe), sorteio determinístico (``classes`` restringe as classes)."""
    grupos: dict[tuple[str, str], list[dict]] = {}
    for r in linhas:
        if r.get("classe") and (classes is None or r["classe"] in classes):
            grupos.setdefault((r["pasta"], r["classe"]), []).append(r)
    saida = {}
    for chave in sorted(grupos):
        rs = sorted(grupos[chave], key=lambda r: r["arquivo"])
        rng = random.Random(f"{seed}|{chave[0]}|{chave[1]}")
        saida[chave] = rs if len(rs) <= n else sorted(rng.sample(rs, n), key=lambda r: r["arquivo"])
    return saida


def montar_painel(caminhos: list[Path], colunas: int = 6, lado: int = 256) -> Image.Image:
    """Monta grade de imagens com rótulos no rodapé de cada célula."""
    linhas_grade = max(1, -(-len(caminhos) // colunas))
    painel = Image.new("RGB", (colunas * lado, linhas_grade * lado), (30, 30, 30))
    d = ImageDraw.Draw(painel)
    for i, p in enumerate(caminhos):
        x, y = (i % colunas) * lado, (i // colunas) * lado
        try:
            img = Image.open(p).convert("RGB")
            img.thumbnail((lado, lado - 14))
            painel.paste(img, (x, y))
            rotulo = Path(p).name
        except (OSError, ValueError):
            d.rectangle([x, y, x + lado - 1, y + lado - 1], fill=(90, 90, 90))
            rotulo = "ilegível"
        d.text((x + 3, y + lado - 13), rotulo[:40], fill=(255, 255, 0))
    return painel


def ler_exclusoes(csv_path: Path) -> set[tuple[str, str]]:
    """Lê revisao.csv e retorna (pasta, arquivo) marcadas com excluir=1/sim/s/x."""
    if not Path(csv_path).is_file():
        return set()
    with open(csv_path, newline="") as f:
        return {(r["pasta"], r["arquivo"]) for r in csv.DictReader(f) if (r.get("excluir") or "").strip().lower() in MARCAS_EXCLUIR}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", type=Path, action="append", required=True)
    ap.add_argument("--raiz-frames", type=Path, default=RAIZ / "ml/data/raw/coleta_fixa")
    ap.add_argument("--saida", type=Path, default=RAIZ / "ml/data/review/camera_fixa")
    ap.add_argument("--n", type=int, default=24)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    args.saida.mkdir(parents=True, exist_ok=True)
    rev_path = args.saida / "revisao.csv"
    anteriores = {}
    if rev_path.is_file():
        with open(rev_path, newline="") as f:
            anteriores = {(r["pasta"], r["arquivo"]): r for r in csv.DictReader(f)}

    novas = dict(anteriores)
    for man in args.manifest:
        with open(man, newline="") as f:
            linhas = list(csv.DictReader(f))
        for (cam, classe), rs in amostrar_por_grupo(linhas, args.n, args.seed, classes_do_manifest(man.name)).items():
            caminhos = [args.raiz_frames / r["pasta"] / r["arquivo"] for r in rs]
            montar_painel(caminhos).save(args.saida / f"painel_{man.stem}_{cam}_{classe}.jpg", quality=85)
            for r in rs:
                chave = (r["pasta"], r["arquivo"])
                novas.setdefault(chave, {"pasta": r["pasta"], "arquivo": r["arquivo"], "camera": cam,
                                         "classe": classe, "manifest": man.name, "excluir": "", "motivo": ""})
    with open(rev_path, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=COLUNAS_REVISAO)
        wr.writeheader()
        for chave in sorted(novas):
            wr.writerow({k: novas[chave].get(k, "") for k in COLUNAS_REVISAO})
    print(f"[revisão] {len(novas)} frames em {rev_path.relative_to(RAIZ)}; painéis em {args.saida.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
