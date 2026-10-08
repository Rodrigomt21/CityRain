"""Métricas do modelo de câmera fixa por partição, câmera e período (NumPy puro)."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from cityrain_ml.evaluation.metricas import (
    acuracia_chuva_vs_seco,
    kappa_quadratico,
    matriz_confusao,
    recall_classe,
    resumo_classificacao,
    score_intensidade,
    spearman,
)


def _indices(linhas: list[dict], classes: Sequence[str]) -> list[int]:
    return [i for i, r in enumerate(linhas) if r["classe"] in classes]


def _recorte(linhas, probs, classes, chave) -> dict:
    grupos: dict[str, list[int]] = {}
    for i, r in enumerate(linhas):
        grupos.setdefault(r.get(chave) or "?", []).append(i)
    saida = {}
    for g, idx in sorted(grupos.items()):
        y = [classes.index(linhas[i]["classe"]) for i in idx]
        res = resumo_classificacao(y, probs[idx], classes)
        saida[g] = {"n": res["n"], "f1_macro": res["f1_macro"], "acuracia": res["acuracia"]}
    return saida


def metricas_particao(linhas: list[dict], probs: np.ndarray, classes: Sequence[str]) -> dict:
    classes = list(classes)
    idx = _indices(linhas, classes)
    if not idx:
        return {"n": 0}
    linhas = [linhas[i] for i in idx]
    probs = np.asarray(probs)[idx]
    y = [classes.index(r["classe"]) for r in linhas]
    pred = probs.argmax(1)
    m = matriz_confusao(y, pred, len(classes))
    mm = [float(r["mm_h"]) if r.get("mm_h") not in (None, "") else np.nan for r in linhas]
    ok = [i for i, v in enumerate(mm) if not np.isnan(v)]
    sc = score_intensidade(probs)
    return {
        "n": len(y),
        "resumo": resumo_classificacao(y, probs, classes),
        "qwk": kappa_quadratico(y, pred, len(classes)),
        "acuracia_chuva_vs_seco": acuracia_chuva_vs_seco(y, pred, classes.index("seco")) if "seco" in classes else None,
        "recall_forte": recall_classe(m, classes.index("forte")) if "forte" in classes else None,
        "spearman_score_mm_h": spearman([sc[i] for i in ok], [mm[i] for i in ok]) if len(ok) > 2 else None,
        "por_periodo": _recorte(linhas, probs, classes, "periodo"),
        "por_camera": _recorte(linhas, probs, classes, "camera"),
    }


def bootstrap_eventos(linhas: list[dict], probs: np.ndarray, classes: Sequence[str], n: int = 1000, seed: int = 0) -> dict:
    """IC 95% reamostrando eventos inteiros (a unidade estatística do projeto)."""
    classes = list(classes)
    idx = _indices(linhas, classes)
    linhas = [linhas[i] for i in idx]
    probs = np.asarray(probs)[idx]
    por_ev: dict[str, list[int]] = {}
    for i, r in enumerate(linhas):
        por_ev.setdefault(r["evento_id"], []).append(i)
    eventos = sorted(por_ev)
    rng = np.random.default_rng(seed)
    f1s, recs = [], []
    for _ in range(n):
        amostra = rng.choice(len(eventos), size=len(eventos), replace=True)
        ii = [i for e in amostra for i in por_ev[eventos[e]]]
        y = [classes.index(linhas[i]["classe"]) for i in ii]
        m = matriz_confusao(y, probs[ii].argmax(1), len(classes))
        f1s.append(resumo_classificacao(y, probs[ii], classes)["f1_macro"])
        r = recall_classe(m, classes.index("forte")) if "forte" in classes else None
        if r is not None:
            recs.append(r)

    def _ic(v):
        return {"media": float(np.mean(v)), "ic95": [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]} if v else None

    return {"n_eventos": len(eventos), "f1_macro": _ic(f1s), "recall_forte": _ic(recs)}
