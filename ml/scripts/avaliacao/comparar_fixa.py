#!/usr/bin/env python3
"""Comparação PAREADA entre dois experimentos do modelo de câmera fixa (4 classes).

ATENÇÃO: este script é para o modelo de câmera fixa (seco | garoa | moderada | forte). O
``intervalos_confianca.py`` é a ferramenta de 3 classes do modelo do CARRO (v3) e não serve aqui.

Lê ``predicoes_test_ircnn.csv`` dos 4 folds de cada experimento (cada evento do irCNN foi testado
uma vez, fora do treino), casa os frames por ``caminho`` (exige exatamente os mesmos frames nos
dois: por isso F1, F2 e F3 usam ``exigir_referencia`` e excluem o evento da referência) e
reamostra EVENTOS com o mesmo sorteio para A e B. Resultado: diferença A - B de F1 macro e de
recall de forte, com IC 95% bootstrap, em ``ml/resultados/fixa_comparacao_<a>_vs_<b>.json``.

Cada lado aceita um diretório de CV (``ml/runs/<nome>__cv_<ts>/``, com ``metricas_cv.json``) ou a
lista dos runs dos folds.

Nota para a comparação com o F0 (v3 de 3 classes): F0 nunca prevê ``seco``; compare-o com o bloco
``chuva_apenas`` de ``metricas_particao`` (as linhas de chuva com as predições de 4 classes, onde
prever ``seco`` conta como erro), nunca com o F1 macro de 4 classes.

Uso:
    ml/.venv/bin/python ml/scripts/avaliacao/comparar_fixa.py \
        --a ml/runs/fixa_f3_mnv3_ref__cv_20261010_120000 --b ml/runs/fixa_f1_mnv3__cv_20261010_110000
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "ml" / "src"))

from cityrain_ml.data.fixa import CLASSES_FIXA  # noqa: E402
from cityrain_ml.evaluation.fixa import bootstrap_pareado  # noqa: E402


def resolver_runs(entradas: list[Path]) -> list[Path]:
    """Um diretório de CV vira a lista dos runs dos folds; senão as entradas já são os runs."""
    if len(entradas) == 1 and (entradas[0] / "metricas_cv.json").exists():
        folds = json.loads((entradas[0] / "metricas_cv.json").read_text())["folds"]
        return [entradas[0].parent / nome for nome in folds]
    return list(entradas)


def _ler(runs: list[Path]) -> dict[str, tuple[dict, np.ndarray]]:
    """caminho -> (linha, probabilidades) de todos os folds."""
    saida: dict[str, tuple[dict, np.ndarray]] = {}
    for run in runs:
        with open(run / "predicoes_test_ircnn.csv", newline="") as f:
            for r in csv.DictReader(f):
                if r["caminho"] in saida:
                    raise ValueError(f"caminho em mais de um fold: {r['caminho']}")
                saida[r["caminho"]] = (r, np.array([float(r[f"p_{c}"]) for c in CLASSES_FIXA]))
    return saida


def comparar(runs_a: list[Path], runs_b: list[Path], n: int = 1000, seed: int = 0) -> dict:
    """Diferença pareada A - B; levanta ValueError se os dois não cobrem os mesmos ``caminho``."""
    a, b = _ler(runs_a), _ler(runs_b)
    if set(a) != set(b):
        so_a, so_b = sorted(set(a) - set(b)), sorted(set(b) - set(a))
        raise ValueError(f"os experimentos não cobrem os mesmos caminho: {len(so_a)} só em A (ex. {so_a[:3]}), "
                         f"{len(so_b)} só em B (ex. {so_b[:3]})")
    caminhos = sorted(a)
    linhas = [a[c][0] for c in caminhos]
    r = bootstrap_pareado(linhas, np.stack([a[c][1] for c in caminhos]), np.stack([b[c][1] for c in caminhos]),
                          CLASSES_FIXA, n=n, seed=seed)
    return {"n_linhas": len(caminhos), "n_bootstrap": n, "seed": seed, **r}


def _rotulo(entradas: list[Path]) -> str:
    base = entradas[0].name
    return re.sub(r"(_fold\w+)?__.*$", "", base)


def salvar(resultado: dict, nome_a: str, nome_b: str, destino: Path) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    arq = destino / f"fixa_comparacao_{nome_a}_vs_{nome_b}.json"
    arq.write_text(json.dumps({"a": nome_a, "b": nome_b, **resultado}, indent=2, ensure_ascii=False))
    return arq


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--a", type=Path, nargs="+", required=True, help="diretório de CV ou runs dos folds do experimento A")
    ap.add_argument("--b", type=Path, nargs="+", required=True, help="idem, experimento B")
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    r = comparar(resolver_runs(args.a), resolver_runs(args.b), args.n, args.seed)
    arq = salvar(r, _rotulo(args.a), _rotulo(args.b), RAIZ / "ml" / "resultados")
    for k in ("diferenca_f1_macro", "diferenca_recall_forte"):
        v = r[k]
        print(f"{k:24s} " + ("sem dados" if v is None else f"{v['media']:+.3f}  IC95 [{v['ic95'][0]:+.3f}, {v['ic95'][1]:+.3f}]"))
    print(f"[ok] {arq}")


if __name__ == "__main__":
    main()
