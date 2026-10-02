#!/usr/bin/env python3
"""Teste de ordenação do D7: mede os sintéticos com a MESMA régua do D6.

Gera N amostras por classe (seeds fixas, bases de treino), mede cada uma com
`medir_regua.medir_imagem` e compara com a base. A spec exige que as métricas de
`moderada` fiquem entre garoa real e `forte`, e que `forte` caia na faixa de
23/09/YouTube. Salva a tabela em
`ml/data/review/sintetico_v1/regua_sinteticos.json`.

Uso:
    ml/.venv/bin/python ml/scripts/sintetico/validar_regua.py [--n 30]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[2]
sys.path.insert(0, str(RAIZ / "ml" / "src"))
sys.path.insert(0, str(AQUI))

import gerar  # noqa: E402
from cityrain_ml.data.sintetico import carregar_banco_formas, gerar_amostra, sortear_mm_h_alvo  # noqa: E402
from cityrain_ml.data import sintetico as _sint  # noqa: E402

METRICAS = ("gotas_mp", "contraste_local", "var_laplaciano", "cobertura_grande")


def cobertura_grande(regua, bgr: np.ndarray, sigma: float = 2.5, k: float = 2.0, limiar: float = 0.02) -> float:
    """Fração da ROI coberta por estruturas "de gota grande" (DoG em escala maior).

    O detector do D6 só pega gotas pequenas e nítidas (raio <= 4 px); gotas
    grandes e borradas, coalescidas ou escorridas passam batido. Esta métrica
    complementar usa |G(sigma) - G(k·sigma)| > limiar sobre fundo SEM
    gradiente forte (rejeita bordas de objetos: só conta onde o gradiente
    local suavizado é baixo). É relativa: serve para comparar base/moderada/
    forte/YouTube na mesma normalização, não para contar gotas.
    """
    img = regua.recortar_roi(regua.normalizar(bgr, regua.PARAMS["largura_norm"]))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    dog = np.abs(cv2.GaussianBlur(gray, (0, 0), sigma) - cv2.GaussianBlur(gray, (0, 0), sigma * k))
    gx = cv2.Sobel(cv2.GaussianBlur(gray, (0, 0), 1.0), cv2.CV_32F, 1, 0)
    gy = cv2.Sobel(cv2.GaussianBlur(gray, (0, 0), 1.0), cv2.CV_32F, 0, 1)
    grad = cv2.GaussianBlur(np.hypot(gx, gy), (0, 0), 6.0)
    liso = grad < float(np.percentile(grad, 60))
    return float(((dog > limiar) & liso).mean())


def medir_completo(regua, bgr: np.ndarray) -> dict:
    """Métricas da régua do D6 mais a cobertura de gotas grandes."""
    m = regua.medir_imagem(bgr)
    m["cobertura_grande"] = cobertura_grande(regua, bgr)
    return m


def _carregar_regua():
    spec = importlib.util.spec_from_file_location("medir_regua", AQUI / "medir_regua.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["medir_regua"] = mod
    spec.loader.exec_module(mod)
    return mod


def medir_referencias(regua, passo: int = 4) -> dict[str, dict[str, float]]:
    """Mede as referências reais de chuva forte (YouTube D5: 7, 8, 11-pico, 13) e 23/09.

    Args:
        regua: Módulo ``medir_regua`` carregado.
        passo: Usa 1 frame a cada ``passo`` (frames a 1 fps são quase iguais).

    Returns:
        Mapa referência -> média de cada métrica de :data:`METRICAS`.
    """
    import csv
    from collections import defaultdict

    grupos: dict[str, list[Path]] = defaultdict(list)
    with open(RAIZ / "ml/data/manifests/manifest_youtube_ordinal.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["trecho"] in ("unico", "pico"):
                grupos[r["video"].replace("youtube_", "yt_")].append(RAIZ / "ml" / r["caminho"])
    grupos["real_2309"] = sorted((RAIZ / "ml/data/processed/imt_coleta/cityrain_frames4").glob("frame_20260923_*.jpg"))
    saida = {}
    for nome, caminhos in grupos.items():
        meds = [medir_completo(regua, cv2.imread(str(p))) for p in caminhos[::passo]]
        saida[nome] = {k: float(np.nanmean([m[k] for m in meds])) for k in METRICAS}
        saida[nome]["n"] = len(meds)
    return saida


def medir_sinteticos(cfg: dict[str, Any], n: int = 30) -> dict[str, Any]:
    """Gera ``n`` sintéticos por classe e devolve média/desvio das métricas da régua.

    Args:
        cfg: Config carregada de ``sintetico_v1.yaml``.
        n: Amostras por classe (as mesmas ``n`` bases, espaçadas, para base e classes).

    Returns:
        Dict com ``base``, ``moderada`` e ``forte``; cada um mapeia métrica ->
        ``{media, desvio}``, mais ``n`` e as listas brutas em ``valores``.
    """
    regua = _carregar_regua()
    bases = gerar.listar_bases(cfg)
    idx = np.linspace(0, len(bases) - 1, n).round().astype(int)
    g = cfg["camadas"]["gotas"]
    banco = carregar_banco_formas(
        _sint._resolver_dir(g["formas_dir"]), g["n_formas"], g["passo_arquivos"], g.get("frac_mascaras", 0.2)
    )
    todas = METRICAS + ("cobertura_agua",)  # a última vem dos parâmetros das camadas (base = 0)
    valores: dict[str, dict[str, list[float]]] = {
        k: {m: [] for m in todas} for k in ("base", "moderada", "forte")
    }
    for classe in ("moderada", "forte"):
        rng = np.random.default_rng([cfg["amostragem"]["seed_global"], 7, 0 if classe == "moderada" else 1])
        for k, i in enumerate(idx):
            lin = bases[i]
            img = cv2.imread(str(gerar.caminho_base(cfg, lin)))
            mm_alvo = sortear_mm_h_alvo(classe, rng, cfg["amostragem"]["faixas_mm_h"])
            r = gerar_amostra(img, float(lin["mm_h"]), mm_alvo, 5000 + k, cfg, banco)
            med = medir_completo(regua, r.imagem)
            for m in METRICAS:
                valores[classe][m].append(med[m])
            valores[classe]["cobertura_agua"].append(r.parametros["cobertura_agua"])
            if classe == "moderada":
                mb = medir_completo(regua, img)
                for m in METRICAS:
                    valores["base"][m].append(mb[m])
                valores["base"]["cobertura_agua"].append(0.0)
    saida: dict[str, Any] = {"n": n, "referencias": medir_referencias(regua)}
    for k, d in valores.items():
        saida[k] = {m: {"media": float(np.mean(v)), "desvio": float(np.std(v))} for m, v in d.items()}
    saida["valores"] = valores
    return saida


def main() -> None:
    """Mede, imprime a tabela e salva o JSON."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--config", type=Path, default=RAIZ / "ml/configs/sintetico_v1.yaml")
    args = ap.parse_args()
    cfg = gerar.carregar_config(args.config)
    res = medir_sinteticos(cfg, args.n)
    destino = RAIZ / cfg["saida"]["review_dir"] / "regua_sinteticos.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    for k in ("base", "moderada", "forte"):
        print(k.ljust(9), "  ".join(f"{m}={res[k][m]['media']:.3f}±{res[k][m]['desvio']:.3f}" for m in METRICAS + ("cobertura_agua",)))
    for k, v in res["referencias"].items():
        print(k.ljust(12), "  ".join(f"{m}={v[m]:.3f}" for m in METRICAS))


if __name__ == "__main__":
    main()
