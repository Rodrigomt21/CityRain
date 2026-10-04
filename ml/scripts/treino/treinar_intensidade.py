#!/usr/bin/env python3
"""CLI do treino do modelo de intensidade (garoa | moderada | forte).

Uso:
    ml/.venv/bin/python ml/scripts/treino/treinar_intensidade.py ml/configs/treino_intensidade_v1_mnv3.yaml
    ml/.venv/bin/python ml/scripts/treino/treinar_intensidade.py <config> --avaliar ml/runs/<run>/melhor.pt
    # validação cruzada por evento do irCNN (config com dados.ircnn_cv):
    ml/.venv/bin/python ml/scripts/treino/treinar_intensidade.py ml/configs/treino_intensidade_cv_mnv3.yaml --cv

Saída em ``ml/runs/<nome>__<timestamp>/`` (gitignored): config, histórico,
checkpoint, métricas e predições por partição. Com ``--cv``, um run por fold e
``ml/runs/<nome>__cv_<timestamp>/metricas_cv.json`` com o irCNN agregado. Ver
``ml/src/cityrain_ml/training/intensidade.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "ml" / "src"))

from cityrain_ml.training.intensidade import agregar_cv, executar  # noqa: E402


def _imprimir(saida: Path) -> None:
    met = json.loads((saida / "metricas.json").read_text())
    print(f"\n[ok] {saida.relative_to(RAIZ)}")
    for p, r in met["classificacao"].items():
        if "f1_macro" in r:
            print(f"  {p:22s} F1 macro {r['f1_macro']:.3f}  acc {r['acuracia']:.3f}  (n={r['n']})")
    for k, v in met["ordenacao"].items():
        if not isinstance(v, dict):
            print(f"  {k:34s} {v:.3f}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config", type=Path)
    ap.add_argument("--avaliar", type=Path, help="só avalia este checkpoint (não treina)")
    ap.add_argument("--fold", type=int, help="roda só este fold do ircnn_cv")
    ap.add_argument("--cv", action="store_true", help="roda todos os folds do ircnn_cv e agrega")
    args = ap.parse_args()
    config = args.config.resolve()

    if not args.cv:
        saida = executar(config, RAIZ, args.avaliar.resolve() if args.avaliar else None, args.fold)
        _imprimir(saida)
        return

    cfg = yaml.safe_load(config.read_text())
    runs = []
    for k in range(len(cfg["dados"]["ircnn_cv"]["folds"])):
        print(f"\n===== fold {k} =====")
        runs.append(executar(config, RAIZ, fold=k))
        _imprimir(runs[-1])
    destino = RAIZ / "ml" / "runs" / f"{cfg['nome']}__cv_{datetime.now():%Y%m%d_%H%M%S}"
    met = agregar_cv(runs, destino)
    r = met["test_ircnn_agregado"]
    print(f"\n[cv] {destino.relative_to(RAIZ)}")
    print(f"  irCNN agregado (12 eventos)  F1 macro {r['f1_macro']:.3f}  acc {r['acuracia']:.3f}  (n={r['n']})")
    print(f"  F1 por classe {r['f1_por_classe']}")
    print(f"  Spearman score x mm/h {met['ircnn_spearman_score_vs_mm_h']:.3f}")
    for k, v in met["por_fold"].items():
        print(f"  {k:40s} {v['media']:.3f} ± {v['desvio']:.3f}")


if __name__ == "__main__":
    main()
