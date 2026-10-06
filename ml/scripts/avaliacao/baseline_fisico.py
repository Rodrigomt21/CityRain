#!/usr/bin/env python3
"""Baseline sem deep learning: atributos físicos da imagem + regressão logística.

Responde "a CNN vale a pena?" com o MESMO protocolo da CV v3 (mesmos folds por
evento do irCNN, mesmas linhas de treino via ``montar_particoes``). Atributos por
frame (``medir_regua.medir_imagem`` + 3 globais):

- gotas por megapixel, raio médio/p90 e fração de gotas grandes (vidro);
- contraste RMS, contraste ao longe (horizonte) e nitidez (var. do Laplaciano);
- brilho e saturação médios; dark channel médio (proxy de névoa, He et al. 2009).

Uso:
    ml/.venv/bin/python ml/scripts/avaliacao/baseline_fisico.py ml/configs/treino_intensidade_cv_v3_mnv3.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import yaml
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "ml" / "src"))
sys.path.insert(0, str(RAIZ / "ml" / "scripts" / "sintetico"))

from cityrain_ml.data.intensidade import ler_split  # noqa: E402
from cityrain_ml.evaluation.metricas import CLASSES, resumo_classificacao, score_intensidade, spearman, taxa_ordenacao  # noqa: E402
from cityrain_ml.training.intensidade import eventos_ircnn, montar_particoes  # noqa: E402


def atributos(caminho: str) -> list[float]:
    from medir_regua import medir_imagem, normalizar  # import no processo filho

    bgr = cv2.imread(str(RAIZ / caminho))
    r = medir_imagem(bgr)
    img = normalizar(bgr)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    dark = cv2.erode(img.min(axis=2), np.ones((15, 15), np.uint8))
    chaves = ("gotas_mp", "raio_medio_px", "raio_p90_px", "frac_gotas_grandes", "contraste_rms", "contraste_local", "var_laplaciano")
    base = [0.0 if not np.isfinite(r[k]) else float(r[k]) for k in chaves]  # sem gota: raio = nan -> 0
    return base + [float(hsv[..., 2].mean() / 255), float(hsv[..., 1].mean() / 255), float(dark.mean() / 255)]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config", type=Path)
    ap.add_argument("--saida", type=Path, default=RAIZ / "ml/resultados/baseline_fisico.json")
    ap.add_argument("--predicoes-dir", type=Path, help="grava probabilidades por frame e fold (para ensemble)")
    args = ap.parse_args()
    cfg = yaml.safe_load(args.config.read_text())
    csv_path = RAIZ / cfg["dados"]["splits_csv"]

    todas = {r["caminho"]: r for r in ler_split(csv_path)
             if r["particao"] in ("train", "val", "test_real", "test_ircnn", "test_ordinal_2309", "test_ordinal_youtube")
             and (r["particao"] != "train" or r["origem"] in ("real", "sintetico"))}
    caminhos = sorted(todas)
    print(f"[baseline] extraindo atributos de {len(caminhos)} frames...", flush=True)
    with ProcessPoolExecutor() as ex:
        X = dict(zip(caminhos, ex.map(atributos, caminhos, chunksize=64)))
    print("[baseline] atributos ok", flush=True)

    def mat(linhas):
        return np.array([X[r["caminho"]] for r in linhas], dtype=np.float64)

    teste_real = ler_split(csv_path, {"test_real"})
    o2309, oyt = ler_split(csv_path, {"test_ordinal_2309"}), ler_split(csv_path, {"test_ordinal_youtube"})
    ir_todos = [r for r in ler_split(csv_path, {"test_ircnn"}) if r["classe"] in CLASSES]
    y_ag, p_ag, mm_ag, por_fold = [], [], [], []
    for k in range(len(cfg["dados"]["ircnn_cv"]["folds"])):
        cfg["dados"]["ircnn_cv"]["fold"] = k
        tr, va = montar_particoes(cfg, csv_path)
        clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced"))
        clf.fit(mat(tr), [CLASSES.index(r["classe"]) for r in tr])
        teste = [r for r in ir_todos if r["evento_id"] in eventos_ircnn(cfg)["test"]]
        p = clf.predict_proba(mat(teste))
        y = [CLASSES.index(r["classe"]) for r in teste]
        y_ag += y; p_ag.append(p); mm_ag += [float(r["mm_h"]) for r in teste]
        s13, s23, syt = (score_intensidade(clf.predict_proba(mat(l))) for l in (teste_real, o2309, oyt))
        if args.predicoes_dir:
            args.predicoes_dir.mkdir(parents=True, exist_ok=True)
            for nome, l in (("val", va), ("test_ircnn", teste), ("test_real", teste_real), ("test_ordinal_2309", o2309), ("test_ordinal_youtube", oyt)):
                pr = clf.predict_proba(mat(l))
                pd.DataFrame({"caminho": [r["caminho"] for r in l], **{f"p_{c}": pr[:, i] for i, c in enumerate(CLASSES)}}).to_csv(
                    args.predicoes_dir / f"fold{k}_{nome}.csv", index=False)
        por_fold.append({
            "ircnn_f1": resumo_classificacao(y, p)["f1_macro"],
            "test_real_f1": resumo_classificacao([0] * len(teste_real), clf.predict_proba(mat(teste_real)))["f1_macro"],
            "2309_maior_1309": taxa_ordenacao(s23, s13),
            "youtube_maior_1309": taxa_ordenacao(syt, s13),
            "youtube_pico_maior_inicio": taxa_ordenacao(
                [s for s, r in zip(syt, oyt) if r["trecho"] == "pico"], [s for s, r in zip(syt, oyt) if r["trecho"] == "inicio"]),
        })
        print(f"[baseline] fold {k}: {json.dumps({a: round(b, 3) for a, b in por_fold[-1].items()})}", flush=True)
    P = np.concatenate(p_ag)
    res = {"irCNN_agregado": resumo_classificacao(y_ag, P), "spearman_score_mm_h": spearman(score_intensidade(P), mm_ag),
           "media_folds": {k: float(np.mean([f[k] for f in por_fold])) for k in por_fold[0]}, "por_fold": por_fold}
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps(res, indent=2, ensure_ascii=False))
    print(f"[baseline] irCNN F1 macro {res['irCNN_agregado']['f1_macro']:.3f} | por classe "
          f"{ {k: round(v, 3) for k, v in res['irCNN_agregado']['f1_por_classe'].items()} } | Spearman {res['spearman_score_mm_h']:.3f}")
    print(f"[baseline] médias: {json.dumps({k: round(v, 3) for k, v in res['media_folds'].items()})}")


if __name__ == "__main__":
    main()
