#!/usr/bin/env python3
"""CLI do gerador sintético de chuva (spec D7).

Subcomandos:
    escada  Gera a escada visual (12 bases x base|~5|~20|~40 mm/h + referências
            reais) em ``ml/data/review/sintetico_v1/escada.jpg``. É o que o
            Rodrigo precisa aprovar ANTES de gerar o volume.
    volume  Gera o dataset final em ``ml/data/synthetic/intensidade_v1/`` com
            manifest CSV. Exige ``--escada-aprovada`` para não gerar por engano.

Uso:
    ml/.venv/bin/python ml/scripts/sintetico/gerar.py escada
    ml/.venv/bin/python ml/scripts/sintetico/gerar.py volume --escada-aprovada
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "ml" / "src"))

from cityrain_ml.data.sintetico import (  # noqa: E402
    carregar_banco_formas,
    gerar_amostra,
    sortear_mm_h_alvo,
)
from cityrain_ml.data import sintetico as _sint  # noqa: E402

REF_2309 = [
    ("real 23/09", "ml/data/processed/imt_coleta/cityrain_frames4/frame_20260923_095929_257.jpg"),
    ("real 23/09", "ml/data/processed/imt_coleta/cityrain_frames4/frame_20260923_100551_833.jpg"),
]


def referencias_youtube() -> list[tuple[str, str]]:
    """Frames YouTube do D5 (7, 8, 11-pico, 13): o do meio de cada vídeo, e um 2º do 11-pico."""
    with open(RAIZ / "ml/data/manifests/manifest_youtube_ordinal.csv", newline="", encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    por: dict[str, list[str]] = {}
    for r in linhas:
        if r["trecho"] in ("unico", "pico"):
            por.setdefault(r["video"], []).append("ml/" + r["caminho"])
    meio = lambda v, f=0.5: por[v][int(len(por[v]) * f)]  # noqa: E731
    return [
        ("YT7 forte", meio("youtube_frames7")),
        ("YT8 forte", meio("youtube_frames8")),
        ("YT11 pico", meio("youtube_frames11")),
        ("YT13 forte", meio("youtube_frames13")),
        ("YT11 pico", meio("youtube_frames11", 0.9)),
        ("YT7 forte", meio("youtube_frames7", 0.2)),
    ]


def carregar_config(caminho: Path) -> dict[str, Any]:
    """Lê o YAML do experimento."""
    with open(caminho, encoding="utf-8") as f:
        return yaml.safe_load(f)


def listar_bases(cfg: dict[str, Any], particao: str = "train") -> list[dict[str, str]]:
    """Frames garoa reais da partição de treino, ordenados (determinístico).

    Por que ordenar por (pasta, arquivo): a escolha de bases da escada e do
    volume precisa ser a mesma em qualquer máquina.
    """
    ent = cfg["entrada"]
    with open(RAIZ / ent["manifest"], newline="", encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    # Com `splits_csv` a partição manda (inclusive `val`); sem ele, cai no corte
    # de horário do train.
    corte = None if ent.get("splits_csv") else ent.get("hora_local_max")
    bases = [
        r
        for r in linhas
        if r["classe"] == ent["classe_base"]
        and r["evento_id"].startswith(ent["evento_prefixo"])
        and (corte is None or r["arquivo"].split("_")[2] < str(corte))
    ]
    # Com `splits_csv`, só entram bases que estão de fato na partição `train`
    # real do D3 — que aplica stride de 2 s. Sem isso o volume usaria frames
    # do bloco de treino que o split descartou, e o `montar_splits.py` recusa
    # sintético cuja base não está no train.
    splits = ent.get("splits_csv")
    if splits:
        with open(RAIZ / splits, newline="", encoding="utf-8") as f:
            no_train = {
                r["caminho"]
                for r in csv.DictReader(f)
                if r["particao"] == particao and r["origem"] == "real"
            }
        bases = [
            r for r in bases
            if f'{ent["imagens_dir"]}/{r["pasta"]}/{r["arquivo"]}' in no_train
        ]
    return sorted(bases, key=lambda r: (r["pasta"], r["arquivo"]))


def caminho_base(cfg: dict[str, Any], linha: dict[str, str]) -> Path:
    """Caminho da imagem de uma linha do manifest."""
    return RAIZ / cfg["entrada"]["imagens_dir"] / linha["pasta"] / linha["arquivo"]


def _rotulo(img: np.ndarray, texto: str) -> np.ndarray:
    """Escreve um rótulo legível no canto superior esquerdo."""
    out = img.copy()
    cv2.rectangle(out, (0, 0), (8 + 9 * len(texto), 20), (0, 0, 0), -1)
    cv2.putText(out, texto, (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    return out


def cmd_escada(cfg: dict[str, Any], args: argparse.Namespace) -> None:
    """Monta a escada visual: 12 bases x (base | 3 níveis) + linha de referência."""
    bases = listar_bases(cfg)
    n = cfg["amostragem"]["escada_n_bases"]
    # variedade: >= 4 bases de ~2 mm/h (maiores mm_h) e o resto espalhado pelas demais
    altas = [i for i, b in enumerate(bases) if float(b["mm_h"]) >= 1.9]
    outras = [i for i, b in enumerate(bases) if float(b["mm_h"]) < 1.9]
    n_alta = min(4, len(altas))
    sel = [altas[j] for j in np.linspace(0, len(altas) - 1, n_alta).round().astype(int)] if n_alta else []
    resto = n - len(sel)
    sel += [outras[j] for j in np.linspace(0, len(outras) - 1, resto).round().astype(int)]
    idx = sorted(set(sel))
    niveis = cfg["amostragem"]["escada_mm_h"]
    banco = carregar_banco_formas(
        _sint._resolver_dir(cfg["camadas"]["gotas"]["formas_dir"]),
        cfg["camadas"]["gotas"]["n_formas"],
        cfg["camadas"]["gotas"]["passo_arquivos"],
    )
    cel = (args.largura_celula, int(args.largura_celula * 0.75))
    linhas_img = []
    for k, i in enumerate(idx):
        lin = bases[i]
        base = cv2.imread(str(caminho_base(cfg, lin)))
        mm_base = float(lin["mm_h"])
        cels = [_rotulo(cv2.resize(base, cel, interpolation=cv2.INTER_AREA), f"base {mm_base:.1f} mm/h")]
        for mm in niveis:
            r = gerar_amostra(base, mm_base, mm, seed=1000 + k, config=cfg, banco_formas=banco)
            cels.append(_rotulo(cv2.resize(r.imagem, cel, interpolation=cv2.INTER_AREA), f"sint {mm:g} mm/h"))
        linhas_img.append(np.hstack(cels))
    todas = [REF_2309[0]] + referencias_youtube()[:3] + [referencias_youtube()[3], REF_2309[1]] + referencias_youtube()[4:]
    for k in range(0, len(todas), 4):
        refs = []
        for nome, p in todas[k : k + 4]:
            im = cv2.imread(str(RAIZ / p))
            refs.append(_rotulo(cv2.resize(im, cel, interpolation=cv2.INTER_AREA), nome))
        linhas_img.append(np.hstack(refs))
    escada = np.vstack(linhas_img)
    saida = RAIZ / cfg["saida"]["review_dir"]
    saida.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(saida / "escada.jpg"), escada, [cv2.IMWRITE_JPEG_QUALITY, 92])
    print(f"escada: {saida / 'escada.jpg'} ({escada.shape[1]}x{escada.shape[0]})")


def cmd_volume(cfg: dict[str, Any], args: argparse.Namespace) -> None:
    """Gera o volume final e o manifest. Só roda com ``--escada-aprovada``."""
    if not args.escada_aprovada:
        sys.exit("recusado: o volume só é gerado após aprovação da escada (--escada-aprovada)")
    am = cfg["amostragem"]
    bases = listar_bases(cfg, args.particao)
    n_cls = am["n_por_classe"] or len(bases)
    # Cada partição tem diretório e manifest próprios; val nunca reaproveita
    # base nem seed do train.
    sufixo = "" if args.particao == "train" else f"_{args.particao}"
    saida = RAIZ / (cfg["saida"]["dir"] + sufixo)
    saida.mkdir(parents=True, exist_ok=True)
    banco = carregar_banco_formas(
        _sint._resolver_dir(cfg["camadas"]["gotas"]["formas_dir"]),
        cfg["camadas"]["gotas"]["n_formas"],
        cfg["camadas"]["gotas"]["passo_arquivos"],
    )
    linhas_man: list[dict[str, Any]] = []
    for classe in ("moderada", "forte"):
        rng = np.random.default_rng([
            am["seed_global"], 0 if classe == "moderada" else 1,
            0 if args.particao == "train" else 1,
        ])
        # no máximo `max_por_base_por_classe` por base; ciclo determinístico pelas bases
        ordem = [b for _ in range(am["max_por_base_por_classe"]) for b in bases]
        for j in range(min(n_cls, len(ordem))):
            lin = ordem[j]
            seed = int(rng.integers(0, 2**31 - 1))
            mm_alvo = sortear_mm_h_alvo(classe, rng, am["faixas_mm_h"])
            base = cv2.imread(str(caminho_base(cfg, lin)))
            mm_base = float(lin["mm_h"])
            r = gerar_amostra(base, mm_base, mm_alvo, seed, config=cfg, banco_formas=banco)
            nome = f"{classe}_{Path(lin['arquivo']).stem}_{seed % 100000:05d}.jpg"
            (saida / classe).mkdir(exist_ok=True)
            cv2.imwrite(
                str(saida / classe / nome), r.imagem, [cv2.IMWRITE_JPEG_QUALITY, cfg["saida"]["jpeg_qualidade"]]
            )
            linhas_man.append(
                {
                    "base_frame": f"{lin['pasta']}/{lin['arquivo']}",
                    "mm_h_base": mm_base,
                    "mm_h_alvo": mm_alvo,
                    "classe": classe,
                    "seed": seed,
                    "arquivo": f"{classe}/{nome}",
                    "parametros_camadas": json.dumps(r.parametros, ensure_ascii=False, sort_keys=True),
                }
            )
    caminho_man = saida / Path(cfg["saida"]["manifest"]).name
    with open(caminho_man, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas_man[0]))
        w.writeheader()
        w.writerows(linhas_man)
    print(f"{len(linhas_man)} amostras em {saida}; manifest {caminho_man}")


def main() -> None:
    """Ponto de entrada."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=RAIZ / "ml/configs/sintetico_v1.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("escada", help="gera a escada visual para aprovação")
    e.add_argument("--largura-celula", type=int, default=480)
    v = sub.add_parser("volume", help="gera o volume final")
    v.add_argument("--escada-aprovada", action="store_true")
    v.add_argument("--particao", choices=("train", "val"), default="train",
                   help="partição real cujas bases recebem chuva sintética")
    args = ap.parse_args()
    cfg = carregar_config(args.config)
    {"escada": cmd_escada, "volume": cmd_volume}[args.cmd](cfg, args)


if __name__ == "__main__":
    main()
