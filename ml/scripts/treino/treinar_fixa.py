#!/usr/bin/env python3
"""CLI do treino do modelo de câmera fixa (seco | garoa | moderada | forte).

Uso:
    ml/.venv/bin/python ml/scripts/treino/treinar_fixa.py ml/configs/treino_fixa_f1_mnv3.yaml --fold final
    ml/.venv/bin/python ml/scripts/treino/treinar_fixa.py <config> --avaliar ml/runs/<run>/melhor.pt
    # ablação do atalho de câmera (só F3): cada linha recebe a referência de OUTRA câmera
    ml/.venv/bin/python ml/scripts/treino/treinar_fixa.py <config> --avaliar ml/runs/<run>/melhor.pt --referencia-trocada
    # validação cruzada por evento do irCNN (config com dados.ircnn_cv):
    ml/.venv/bin/python ml/scripts/treino/treinar_fixa.py ml/configs/treino_fixa_f1_mnv3.yaml --cv

Saída em ``ml/runs/<nome>__<timestamp>/`` (gitignored). ``--avaliar`` usa os papéis das partições
(fold do irCNN etc.) gravados no checkpoint, não os da config passada, e escreve
``metricas_avaliacao_<timestamp>.json`` sem sobrescrever ``metricas.json`` do run. Com ``--cv``, um run por
fold e ``ml/runs/<nome>__cv_<timestamp>/metricas_cv.json``. Ver
``ml/src/cityrain_ml/training/fixa.py``.
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

from cityrain_ml.training.fixa import agregar_cv_fixa, executar_fixa  # noqa: E402

CHAVES = ("resumo.f1_macro", "qwk", "acuracia_chuva_vs_seco", "recall_forte")


def _fmt(v) -> str:
    return "  -  " if v is None else f"{v:.3f}"


def _imprimir(saida: Path, arquivo: str = "metricas.json") -> None:
    met = json.loads((saida / arquivo).read_text())
    print(f"\n[ok] {saida.relative_to(RAIZ)}")
    for p, r in met["particoes"].items():
        if r.get("n", 0) == 0:
            print(f"  {p:18s} n=0")
            continue
        vals = [r["resumo"]["f1_macro"] if k == "resumo.f1_macro" else r.get(k) for k in CHAVES]
        print(f"  {p:18s} n={r['n']:<5d} F1 macro {_fmt(vals[0])}  QWK {_fmt(vals[1])}  "
              f"chuva x seco {_fmt(vals[2])}  recall forte {_fmt(vals[3])}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config", type=Path)
    ap.add_argument("--avaliar", type=Path, help="só avalia este checkpoint (não treina)")
    ap.add_argument("--fold", help="roda só este fold do ircnn_cv (número) ou 'final' (todos os eventos no treino)")
    ap.add_argument("--referencia-trocada", action="store_true",
                    help="com --avaliar (F3): usa a referência de outra câmera em cada linha (ablação do atalho)")
    ap.add_argument("--cv", action="store_true", help="roda todos os folds do ircnn_cv e agrega")
    args = ap.parse_args()
    config = args.config.resolve()
    if args.referencia_trocada and not args.avaliar:
        ap.error("--referencia-trocada só pode ser usado junto com --avaliar")

    if not args.cv:
        fold = args.fold if args.fold in (None, "final") else int(args.fold)
        saida = executar_fixa(config, RAIZ, args.avaliar.resolve() if args.avaliar else None, fold,
                              args.referencia_trocada)
        if args.avaliar:
            mais_recente = max(saida.glob("metricas_avaliacao_*.json"), key=lambda p: p.stat().st_mtime)
            _imprimir(saida, mais_recente.name)
        else:
            _imprimir(saida)
        return

    cfg = yaml.safe_load(config.read_text())
    runs = []
    for k in range(len(cfg["dados"]["ircnn_cv"]["folds"])):
        print(f"\n===== fold {k} =====")
        runs.append(executar_fixa(config, RAIZ, fold=k))
        _imprimir(runs[-1])
    destino = RAIZ / "ml" / "runs" / f"{cfg['nome']}__cv_{datetime.now():%Y%m%d_%H%M%S}"
    met = agregar_cv_fixa(runs, destino)
    r = met["test_ircnn_agregado"]
    print(f"\n[cv] {destino.relative_to(RAIZ)}")
    if r.get("n", 0):
        print(f"  irCNN agregado  n={r['n']}  F1 macro {_fmt(r['resumo']['f1_macro'])}  QWK {_fmt(r.get('qwk'))}")
    for p in ("test_camera", "test_prospectivo"):
        for k, v in met[p].items():
            print(f"  {p:18s} {k:24s} " + ("sem dados" if v is None else f"{v['media']:.3f} ± {v['desvio']:.3f}"))


if __name__ == "__main__":
    main()
