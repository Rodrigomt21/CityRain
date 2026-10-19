#!/usr/bin/env python3
"""Matrizes de confusão do gate da Jetson e do modelo da câmera fixa, no mesmo estilo da do v14f.

Duas etapas, porque o backend e o matplotlib vivem em ambientes diferentes:

1. Predições do modelo fixo de produção (InferenceService do backend, o mesmo código do Railway)
   na câmera nunca vista (test_camera de fixa_v1.csv, Balneário Camboriú) e no dia de sol de 18/10:
       backend/.venv/bin/python ml/scripts/avaliacao/matrizes_confusao.py prever-fixa
   → docs/assets/matriz-confusao-fixa.json

2. Figuras (fixa a partir do JSON acima; gate a partir de ml/resultados/gate_v4_cv.json):
       python3 ml/scripts/avaliacao/matrizes_confusao.py figuras
   → docs/assets/matriz-confusao-fixa-bc.png, matriz-confusao-fixa-sol.png, matriz-confusao-gate-v4.png

O gate não tem predições salvas por frame: as contagens saem de n × taxa no limiar 0,5, que são
exatas porque as taxas foram calculadas dessas mesmas contagens.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
ASSETS = RAIZ / "docs/assets"
FIXA_JSON = ASSETS / "matriz-confusao-fixa.json"
GATE_JSON = RAIZ / "ml/resultados/gate_v4_cv.json"
CLASSES = ["seco", "garoa", "moderada", "forte"]
NOMES_SESSAO = {"1610": "16/10 dia", "1710m": "17/10 manhã", "0408": "04/08 dia", "0608": "06/08 noite",
                "1309": "13/09", "2309": "23/09", "1610n": "16/10 noite", "1610n2": "16/10 noite2"}


def prever_fixa() -> None:
    sys.path.insert(0, str(Path(__file__).parent))
    import csv
    import glob

    from checar_modelo_fixa import ATUAL, prever, servico

    s = servico(ATUAL)
    teste = [r for r in csv.DictReader(open(RAIZ / "ml/data/splits/fixa_v1.csv")) if r["particao"] == "test_camera"]
    sol = sorted(glob.glob(str(RAIZ / "ml/data/raw/coleta_fixa/*/frame_20261018_*.jpg")))
    saida = {
        "modelo": s.nome if hasattr(s, "nome") else ATUAL.name,
        "bc": {"y": [r["classe"] for r in teste], "p": prever(s, [r["caminho"] for r in teste])},
        "sol": {"p": prever(s, sol)},
    }
    FIXA_JSON.write_text(json.dumps(saida, ensure_ascii=False))
    print(f"[ok] {FIXA_JSON.relative_to(RAIZ)}: BC n={len(teste)}, sol n={len(sol)}")


def desenhar(ax, contagens, linhas, colunas, titulo, rotulo_y, rotulo_x) -> None:
    """Uma matriz com % da linha e (contagem) em cada célula, cor pela % da linha."""
    import numpy as np

    m = np.array(contagens, dtype=float)
    pct = m / np.maximum(m.sum(axis=1, keepdims=True), 1)
    ax.imshow(pct, cmap="Blues", vmin=0, vmax=1.4)
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            cor = "white" if pct[i, j] > 0.5 else "#1a1a1a"
            ax.text(j, i, f"{pct[i, j]:.0%}\n({int(m[i, j])})", ha="center", va="center", color=cor, fontsize=11)
    ax.set_xticks(range(len(colunas)), colunas)
    ax.set_yticks(range(len(linhas)), linhas)
    ax.set_xlabel(rotulo_x)
    ax.set_ylabel(rotulo_y)
    ax.set_title(titulo, fontsize=11)


def figuras() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Câmera fixa: câmera nunca vista (BC). Sem foto forte no teste, então só 3 linhas.
    d = json.loads(FIXA_JSON.read_text())
    y, p = d["bc"]["y"], d["bc"]["p"]
    linhas = [c for c in CLASSES if c in y]
    cont = [[sum(a == l and b == c for a, b in zip(y, p)) for c in CLASSES] for l in linhas]
    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    desenhar(ax, cont, linhas, CLASSES, f"Câmera fixa nunca vista: Balneário Camboriú (n = {len(y)})",
             "rótulo (pluviômetro)", "previsto pelo modelo fixo")
    fig.tight_layout()
    fig.savefig(ASSETS / "matriz-confusao-fixa-bc.png", dpi=110)

    q = d["sol"]["p"]
    fig, ax = plt.subplots(figsize=(6.4, 2.2))
    desenhar(ax, [[q.count(c) for c in CLASSES]], ["seco"], CLASSES,
             f"Dia de sol, 18/10 (n = {len(q)})", "esperado", "previsto pelo modelo fixo")
    fig.tight_layout()
    fig.savefig(ASSETS / "matriz-confusao-fixa-sol.png", dpi=110)

    # Gate v4: uma matriz por fold (uma sessão seca e uma de chuva fora do treino).
    g = json.loads(GATE_JSON.read_text())["folds"]
    fig, axs = plt.subplots(2, (len(g) + 1) // 2, figsize=(4.2 * ((len(g) + 1) // 2), 7.4))
    for ax, f in zip(axs.flat, g):
        ns, nc = f["n_seco"], f["n_chuva"]
        fa, rc = f["t0.5"]["falso_alarme"], f["t0.5"]["recall"]
        cont = [[ns - round(fa * ns), round(fa * ns)], [nc - round(rc * nc), round(rc * nc)]]
        sec, chu = NOMES_SESSAO.get(f["seco_fora"], f["seco_fora"]), NOMES_SESSAO.get(f["chuva_fora"], f["chuva_fora"])
        desenhar(ax, cont, [f"seco\n{sec}", f"chuva\n{chu}"], ["seco", "chuva"], "", "rótulo", "previsto (limiar 0,5)")
    for ax in list(axs.flat)[len(g):]:
        ax.axis("off")
    fig.suptitle("Gate v4 da Jetson: sessões nunca vistas (cada matriz = 1 rodada da validação)", fontsize=12)
    fig.tight_layout()
    fig.savefig(ASSETS / "matriz-confusao-gate-v4.png", dpi=110)
    print("[ok] figuras em docs/assets/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("etapa", choices=["prever-fixa", "figuras"])
    {"prever-fixa": prever_fixa, "figuras": figuras}[ap.parse_args().etapa]()
