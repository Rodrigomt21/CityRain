#!/usr/bin/env python3
"""Intervalos de confiança por bootstrap DE EVENTO para as CVs do irCNN.

Frames do mesmo evento de chuva não são independentes (a 1 frame/5 s, vizinhos são
quase iguais); reamostrar frames daria intervalos estreitos demais. Aqui se
reamostram os 12 EVENTOS com reposição e recalcula-se F1 macro, F1 por classe e
Spearman sobre as predições agregadas dos folds (cada evento foi testado uma vez,
fora do treino). Comparações entre versões são PAREADAS (mesmos eventos sorteados
nas duas), que é o que diz se uma melhora é real.

Uso:
    ml/.venv/bin/python ml/scripts/avaliacao/intervalos_confianca.py \
        --cv v1=intensidade_cv_mnv3 --cv v3=intensidade_cv_v3_mnv3 --referencia v3
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "ml" / "src"))

from cityrain_ml.evaluation.metricas import CLASSES, f1_por_classe, matriz_confusao, spearman  # noqa: E402


def predicoes(nome_cv: str) -> pd.DataFrame:
    """Predições de irCNN dos 4 folds mais recentes de uma CV (cada evento uma vez)."""
    partes = []
    for k in range(4):
        runs = sorted(glob.glob(str(RAIZ / f"ml/runs/{nome_cv}_fold{k}__*")))
        if not runs:
            raise SystemExit(f"sem run do fold {k} para {nome_cv}")
        partes.append(pd.read_csv(Path(runs[-1]) / "predicoes_test_ircnn.csv"))
    df = pd.concat(partes)
    return df[df["classe"].isin(CLASSES)].reset_index(drop=True)


def metricas(df: pd.DataFrame) -> dict[str, float]:
    y = df["classe"].map(CLASSES.index).to_numpy()
    yp = df[[f"p_{c}" for c in CLASSES]].to_numpy().argmax(1)
    m = matriz_confusao(y, yp, len(CLASSES))
    f1 = f1_por_classe(m)
    pres = m.sum(1) > 0
    return {"f1_macro": float(f1[pres].mean()), **{f"f1_{c}": float(f1[i]) for i, c in enumerate(CLASSES)},
            "spearman": spearman(df["score"], df["mm_h"])}


def bootstrap(dfs: dict[str, pd.DataFrame], n: int, seed: int) -> dict[str, np.ndarray]:
    eventos = sorted(next(iter(dfs.values()))["evento_id"].unique())
    grupos = {v: {e: d[d["evento_id"] == e] for e in eventos} for v, d in dfs.items()}
    rng = np.random.default_rng(seed)
    amostras: dict[str, list[dict]] = {v: [] for v in dfs}
    for _ in range(n):
        sorteio = rng.choice(eventos, size=len(eventos), replace=True)
        for v in dfs:  # mesmo sorteio para todas as versões: comparação pareada
            amostras[v].append(metricas(pd.concat([grupos[v][e] for e in sorteio])))
    return {v: pd.DataFrame(a) for v, a in amostras.items()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cv", action="append", required=True, help="rotulo=nome_da_cv")
    ap.add_argument("--referencia", help="rótulo contra o qual as diferenças pareadas são calculadas")
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--saida", type=Path, default=RAIZ / "ml/resultados/intervalos_confianca.json")
    args = ap.parse_args()
    dfs = dict(spec.split("=", 1) for spec in args.cv)
    dfs = {rot: predicoes(nome) for rot, nome in dfs.items()}
    boot = bootstrap(dfs, args.n, args.seed)
    res: dict = {"metodo": f"bootstrap por evento (12 eventos irCNN), {args.n} reamostras, IC 95% percentil", "versoes": {}}
    for v, b in boot.items():
        pontual = metricas(dfs[v])
        res["versoes"][v] = {k: {"valor": pontual[k], "ic95": [float(b[k].quantile(0.025)), float(b[k].quantile(0.975))]} for k in pontual}
        print(f"{v:6s} " + "  ".join(f"{k} {pontual[k]:.3f} [{b[k].quantile(.025):.3f}, {b[k].quantile(.975):.3f}]"
                                       for k in ("f1_macro", "f1_forte", "spearman")))
    if args.referencia:
        ref = boot[args.referencia]
        res["diferencas_pareadas"] = {}
        for v, b in boot.items():
            if v == args.referencia:
                continue
            d = {k: (ref[k] - b[k]) for k in ("f1_macro", "spearman")}
            res["diferencas_pareadas"][f"{args.referencia}-{v}"] = {
                k: {"media": float(x.mean()), "ic95": [float(x.quantile(.025)), float(x.quantile(.975))], "p_maior_que_zero": float((x > 0).mean())}
                for k, x in d.items()}
            print(f"{args.referencia} − {v}: F1 {d['f1_macro'].mean():+.3f} [{d['f1_macro'].quantile(.025):+.3f}, {d['f1_macro'].quantile(.975):+.3f}]"
                  f" (P>0 = {(d['f1_macro'] > 0).mean():.2f}) | Spearman {d['spearman'].mean():+.3f} "
                  f"[{d['spearman'].quantile(.025):+.3f}, {d['spearman'].quantile(.975):+.3f}]")
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
