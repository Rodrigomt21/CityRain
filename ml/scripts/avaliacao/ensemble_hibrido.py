#!/usr/bin/env python3
"""Híbrido por combinação de probabilidades: CNN v3 + baseline físico, nos mesmos folds.

p = w·p_CNN + (1−w)·p_físico. O peso PADRÃO é w = 0,5, fixado ANTES de olhar o teste;
os outros pesos são só análise de sensibilidade (escolher w pelo teste seria vazamento).
Avalia irCNN (agregado dos 4 folds, cada evento fora do treino), garoa 13/09 e as
ordenações (média dos folds), com IC 95% por bootstrap de evento para o F1 do irCNN.

Uso:
    ml/.venv/bin/python ml/scripts/avaliacao/ensemble_hibrido.py \
        --cnn intensidade_cv_v3_mnv3 --fisico ml/runs/baseline_fisico_cv_v3
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

from cityrain_ml.evaluation.metricas import CLASSES, resumo_classificacao, score_intensidade, spearman, taxa_ordenacao  # noqa: E402

P = [f"p_{c}" for c in CLASSES]


def fold_cnn(nome: str, k: int, parte: str) -> pd.DataFrame:
    run = sorted(glob.glob(str(RAIZ / f"ml/runs/{nome}_fold{k}__*")))[-1]
    return pd.read_csv(Path(run) / f"predicoes_{parte}.csv")


def combinar(cnn: pd.DataFrame, fis: pd.DataFrame, w: float) -> pd.DataFrame:
    m = cnn.merge(fis, on="caminho", suffixes=("_c", "_f"))
    for c in CLASSES:
        m[f"p_{c}"] = w * m[f"p_{c}_c"] + (1 - w) * m[f"p_{c}_f"]
    return m


def avaliar(args, w: float) -> dict:
    ir, ords = [], []
    trechos = pd.read_csv(RAIZ / "ml/data/splits/intensidade_v1.csv")[["caminho", "trecho"]]
    for k in range(4):
        f = lambda parte: pd.read_csv(args.fisico / f"fold{k}_{parte}.csv")  # noqa: E731
        ir.append(combinar(fold_cnn(args.cnn, k, "test_ircnn"), f("test_ircnn"), w))
        s13 = score_intensidade(combinar(fold_cnn(args.cnn, k, "test_real"), f("test_real"), w)[P].to_numpy())
        s23 = score_intensidade(combinar(fold_cnn(args.cnn, k, "test_ordinal_2309"), f("test_ordinal_2309"), w)[P].to_numpy())
        yt = combinar(fold_cnn(args.cnn, k, "test_ordinal_youtube"), f("test_ordinal_youtube"), w).merge(trechos, on="caminho")
        syt = score_intensidade(yt[P].to_numpy())
        ords.append({"2309_maior_1309": taxa_ordenacao(s23, s13), "youtube_maior_1309": taxa_ordenacao(syt, s13),
                     "pico_maior_inicio": taxa_ordenacao(syt[yt["trecho"].to_numpy() == "pico"], syt[yt["trecho"].to_numpy() == "inicio"]),
                     "garoa_1309_acuracia": float(np.mean(score_intensidade(combinar(fold_cnn(args.cnn, k, "test_real"), f("test_real"), w)[P].to_numpy()) < 0.5))})
    df = pd.concat(ir)
    df = df[df["classe"].isin(CLASSES)]
    y = df["classe"].map(CLASSES.index).to_numpy()
    r = resumo_classificacao(y, df[P].to_numpy())
    # IC 95% do F1 macro por bootstrap de evento
    rng = np.random.default_rng(0)
    evs = df["evento_id"].unique()
    grupos = {e: df[df["evento_id"] == e] for e in evs}
    boot = []
    for _ in range(1000):
        d = pd.concat([grupos[e] for e in rng.choice(evs, len(evs))])
        boot.append(resumo_classificacao(d["classe"].map(CLASSES.index).to_numpy(), d[P].to_numpy())["f1_macro"])
    return {"w_cnn": w, "ircnn_f1": r["f1_macro"], "ircnn_f1_ic95": [float(np.quantile(boot, .025)), float(np.quantile(boot, .975))],
            "ircnn_f1_por_classe": r["f1_por_classe"], "spearman": spearman(score_intensidade(df[P].to_numpy()), df["mm_h"]),
            **{k: float(np.mean([o[k] for o in ords])) for k in ords[0]}}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cnn", required=True)
    ap.add_argument("--fisico", type=Path, required=True)
    ap.add_argument("--saida", type=Path, default=RAIZ / "ml/resultados/ensemble_hibrido.json")
    args = ap.parse_args()
    res = [avaliar(args, w) for w in (1.0, 0.75, 0.5, 0.25, 0.0)]
    print(f"{'w_cnn':>6} {'irCNN F1':>9} {'IC95':>15} {'forte':>6} {'Spear':>6} {'23/09>13/09':>11} {'YT>13/09':>8} {'pico>ini':>8} {'garoa13/09':>10}")
    for r in res:
        print(f"{r['w_cnn']:6.2f} {r['ircnn_f1']:9.3f} [{r['ircnn_f1_ic95'][0]:.3f},{r['ircnn_f1_ic95'][1]:.3f}] "
              f"{r['ircnn_f1_por_classe'].get('forte', 0):6.3f} {r['spearman']:6.3f} {r['2309_maior_1309']:11.3f} "
              f"{r['youtube_maior_1309']:8.3f} {r['pico_maior_inicio']:8.3f} {r['garoa_1309_acuracia']:10.3f}")
    args.saida.write_text(json.dumps({"peso_padrao_fixado_antes": 0.5, "resultados": res}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
