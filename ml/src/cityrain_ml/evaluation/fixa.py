"""Métricas do modelo de câmera fixa por partição, câmera e período (NumPy puro)."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from cityrain_ml.evaluation.metricas import (
    acuracia_chuva_vs_seco,
    f1_macro,
    kappa_quadratico,
    matriz_confusao,
    recall_classe,
    resumo_classificacao,
    score_intensidade,
    spearman,
)


def _indices(linhas: list[dict], classes: Sequence[str]) -> list[int]:
    """Índices de linhas cuja classe está em classes."""
    return [i for i, r in enumerate(linhas) if r["classe"] in classes]


def _nan_none(v: float) -> float | None:
    return None if v is None or np.isnan(v) else float(v)


def _recorte(linhas, probs, classes, chave) -> dict:
    """Agrupa linhas por chave e calcula F1 macro, acurácia, QWK e recall de forte para cada grupo."""
    grupos: dict[str, list[int]] = {}
    for i, r in enumerate(linhas):
        grupos.setdefault(r.get(chave) or "?", []).append(i)
    saida = {}
    for g, idx in sorted(grupos.items()):
        y = [classes.index(linhas[i]["classe"]) for i in idx]
        res = resumo_classificacao(y, probs[idx], classes)
        pred = probs[idx].argmax(1)
        m = matriz_confusao(y, pred, len(classes))
        saida[g] = {"n": res["n"], "f1_macro": res["f1_macro"], "acuracia": res["acuracia"],
                    "qwk": _nan_none(kappa_quadratico(y, pred, len(classes))),
                    "recall_forte": recall_classe(m, classes.index("forte")) if "forte" in classes else None}
    return saida


def _chuva_apenas(y: list[int], pred: np.ndarray, classes: list[str]) -> dict:
    """Métricas só nas linhas cuja classe VERDADEIRA é chuva (garoa/moderada/forte).

    Usa as predições de 4 classes: prever ``seco`` para uma linha de chuva é erro.
    É o bloco comparável com o F0 (v3 de 3 classes, que nunca vê o ``seco``). O QWK usa
    a escala completa de 4 níveis e só existe se houver 2+ classes verdadeiras presentes.
    """
    chuva = [k for k, c in enumerate(classes) if c in ("garoa", "moderada", "forte")]
    sel = [i for i, k in enumerate(y) if k in chuva]
    if not sel:
        return {"n": 0}
    yy, pp = [y[i] for i in sel], pred[sel]
    m = matriz_confusao(yy, pp, len(classes))
    return {"n": len(sel), "acuracia": float((np.asarray(yy) == pp).mean()), "f1_macro": f1_macro(m),
            "qwk": _nan_none(kappa_quadratico(yy, pp, len(classes))),
            "recall_forte": recall_classe(m, classes.index("forte")) if "forte" in classes else None}


def metricas_particao(linhas: list[dict], probs: np.ndarray, classes: Sequence[str]) -> dict:
    """Calcula métricas (QWK, acurácia, recall, Spearman) com recortes por câmera e período."""
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
    qwk = kappa_quadratico(y, pred, len(classes))
    spear = spearman([sc[i] for i in ok], [mm[i] for i in ok]) if len(ok) > 2 else None
    # chuva x seco sem depender da prevalência: recall de cada lado e a média dos dois
    rec_seco = rec_chuva = bal = None
    if "seco" in classes:
        iseco = classes.index("seco")
        ya, pa = np.asarray(y), np.asarray(pred)
        if (ya == iseco).any():
            rec_seco = float((pa[ya == iseco] == iseco).mean())
        if (ya != iseco).any():
            rec_chuva = float((pa[ya != iseco] != iseco).mean())
        if rec_seco is not None and rec_chuva is not None:
            bal = (rec_seco + rec_chuva) / 2
    return {
        "n": len(y),
        "resumo": resumo_classificacao(y, probs, classes),
        "qwk": None if np.isnan(qwk) else qwk,
        "acuracia_chuva_vs_seco": acuracia_chuva_vs_seco(y, pred, classes.index("seco")) if "seco" in classes else None,
        "recall_forte": recall_classe(m, classes.index("forte")) if "forte" in classes else None,
        "recall_seco": rec_seco,
        "recall_chuva": rec_chuva,
        "acuracia_balanceada_chuva_seco": bal,
        "chuva_apenas": _chuva_apenas(y, pred, classes),
        "spearman_score_mm_h": None if spear is None or np.isnan(spear) else spear,
        "por_periodo": _recorte(linhas, probs, classes, "periodo"),
        "por_camera": _recorte(linhas, probs, classes, "camera"),
    }


def bootstrap_eventos(linhas: list[dict], probs: np.ndarray, classes: Sequence[str], n: int = 1000, seed: int = 0) -> dict:
    """IC 95% reamostrando eventos inteiros (a unidade estatística do projeto)."""
    classes = list(classes)
    idx = _indices(linhas, classes)
    if not idx:
        return {"n_eventos": 0, "f1_macro": None, "recall_forte": None}
    linhas = [linhas[i] for i in idx]
    probs = np.asarray(probs)[idx]
    por_ev: dict[str, list[int]] = {}
    for i, r in enumerate(linhas):
        por_ev.setdefault(r["evento_id"], []).append(i)
    eventos = sorted(por_ev)
    if not eventos:
        return {"n_eventos": 0, "f1_macro": None, "recall_forte": None}
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


def bootstrap_pareado(linhas: list[dict], probs_a: np.ndarray, probs_b: np.ndarray, classes: Sequence[str],
                      n: int = 1000, seed: int = 0, linhas_b: list[dict] | None = None) -> dict:
    """Diferença A - B (F1 macro e recall de forte) reamostrando eventos, com o MESMO sorteio nos dois.

    ``probs_a`` e ``probs_b`` estão alinhadas a ``linhas``. Se as linhas de B vierem em
    ``linhas_b``, elas precisam ter exatamente os mesmos ``caminho`` na mesma ordem; se não,
    levanta ValueError (comparar modelos em linhas diferentes não é pareado). IC 95% percentil.
    """
    classes = list(classes)
    probs_a, probs_b = np.asarray(probs_a), np.asarray(probs_b)
    if not (len(linhas) == len(probs_a) == len(probs_b)):
        raise ValueError(f"tamanhos diferentes: {len(linhas)} linhas, {len(probs_a)} probs A, {len(probs_b)} probs B")
    caminhos = [r["caminho"] for r in linhas]
    if len(set(caminhos)) != len(caminhos):
        raise ValueError("caminho repetido nas linhas: o pareamento exige um frame por linha")
    if linhas_b is not None and [r["caminho"] for r in linhas_b] != caminhos:
        raise ValueError("os caminho das linhas de A e B não coincidem (mesmos frames, mesma ordem)")
    idx = _indices(linhas, classes)
    linhas = [linhas[i] for i in idx]
    pa, pb = probs_a[idx], probs_b[idx]
    por_ev: dict[str, list[int]] = {}
    for i, r in enumerate(linhas):
        por_ev.setdefault(r["evento_id"], []).append(i)
    eventos = sorted(por_ev)
    if not eventos:
        return {"n_eventos": 0, "diferenca_f1_macro": None, "diferenca_recall_forte": None}
    rng = np.random.default_rng(seed)
    d_f1, d_rec = [], []
    for _ in range(n):
        amostra = rng.choice(len(eventos), size=len(eventos), replace=True)
        ii = [i for e in amostra for i in por_ev[eventos[e]]]
        y = [classes.index(linhas[i]["classe"]) for i in ii]
        ma = matriz_confusao(y, pa[ii].argmax(1), len(classes))
        mb = matriz_confusao(y, pb[ii].argmax(1), len(classes))
        d_f1.append(f1_macro(ma) - f1_macro(mb))
        if "forte" in classes:
            ra, rb = recall_classe(ma, classes.index("forte")), recall_classe(mb, classes.index("forte"))
            if ra is not None and rb is not None:
                d_rec.append(ra - rb)

    def _ic(v):
        v = [x for x in v if not np.isnan(x)]
        return {"media": float(np.mean(v)), "ic95": [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]} if v else None

    return {"n_eventos": len(eventos), "diferenca_f1_macro": _ic(d_f1), "diferenca_recall_forte": _ic(d_rec)}
