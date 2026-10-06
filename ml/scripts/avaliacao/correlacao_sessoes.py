#!/usr/bin/env python3
"""Avalia o modelo no CARRO por correlação ao longo das sessões (não por classe).

Com poucos frames de carro com rótulo de classe confiável, a pergunta que dá para
responder com o que existe é: **quando a chuva medida pelas estações sobe, o score
do modelo sobe junto?** Para cada frame com GPS, compara o score de intensidade do
modelo (classe esperada Σ p_k·k, 0 = garoa … 2 = forte) com o mm/h de referência
das estações na janela de 10 min que contém o frame:

- ``mediana_5km``: mediana das estações a <= ``--raio-km`` (robusta a 1 estação fora);
- ``proxima``: a estação mais próxima (mais local, mais sujeita a erro de posição).

Reporta Spearman por sessão e agregado, e o score médio por faixa de mm/h. Usa o
ONNX de produção (o mesmo do backend), não um checkpoint de treino.

Uso:
    ml/.venv/bin/python ml/scripts/avaliacao/correlacao_sessoes.py
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
import pandas as pd
from PIL import Image

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "ml" / "src"))

from cityrain_ml.evaluation.metricas import score_intensidade, spearman  # noqa: E402

FAIXAS = [(-0.01, 0.0, "0 (seco na rede)"), (0.0, 1.0, "0–1"), (1.0, 2.5, "1–2,5"), (2.5, 6.0, "2,5–6"), (6.0, 10.0, "6–10"), (10.0, 1e9, ">10")]


def _hav_km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = np.sin((lat2 - lat1) * p / 2) ** 2 + np.cos(lat1 * p) * np.cos(lat2 * p) * np.sin((lon2 - lon1) * p / 2) ** 2
    return 2 * 6371 * np.arcsin(np.sqrt(a))


class ModeloOnnx:
    def __init__(self, caminho: Path) -> None:
        self.s = ort.InferenceSession(str(caminho), providers=["CPUExecutionProvider"])
        meta = self.s.get_modelmeta().custom_metadata_map
        self.h, self.w = int(meta["altura"]), int(meta["largura"])
        self.media = np.array(json.loads(meta["media"]), np.float32)
        self.desvio = np.array(json.loads(meta["desvio"]), np.float32)
        self.entrada = self.s.get_inputs()[0].name

    def probs(self, caminhos: list[Path], lote: int = 32) -> np.ndarray:
        saida = []
        for i in range(0, len(caminhos), lote):
            x = np.stack([
                ((np.asarray(Image.open(c).convert("RGB").resize((self.w, self.h), Image.BILINEAR), np.float32) / 255
                  - self.media) / self.desvio).transpose(2, 0, 1)
                for c in caminhos[i:i + lote]
            ])
            z = self.s.run(None, {self.entrada: x})[0]
            e = np.exp(z - z.max(1, keepdims=True))
            saida.append(e / e.sum(1, keepdims=True))
        return np.concatenate(saida)


def referencia(frames: pd.DataFrame, est: pd.DataFrame, raio_km: float) -> pd.DataFrame:
    """mm/h das estações na janela de 10 min de cada frame (mediana no raio e a mais próxima)."""
    est = est.copy()
    est["fim"] = est["ts_utc"]
    est["ini"] = est["fim"] - pd.to_timedelta(est["janela_min"], unit="m")
    est["mm_h"] = est["acumulado_mm"] * 60 / est["janela_min"]
    pos = est.groupby("estacao_id")[["lat", "lon"]].first()
    med, prox, n_est = [], [], []
    for r in frames.itertuples():
        d = pd.Series(_hav_km(r.lat, r.lon, pos["lat"].values, pos["lon"].values), index=pos.index)
        no_raio = d[d <= raio_km]
        janela = est[(est["ini"] < r.ts) & (est["fim"] >= r.ts) & est["estacao_id"].isin(no_raio.index)]
        v = janela.set_index("estacao_id")["mm_h"]
        med.append(float(v.median()) if len(v) else np.nan)
        n_est.append(len(v))
        prox.append(float(v[no_raio.loc[v.index].idxmin()]) if len(v) else np.nan)
    return frames.assign(mm_h_mediana=med, mm_h_proxima=prox, n_estacoes=n_est)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", type=Path, default=RAIZ / "ml/data/manifests/manifest_imt.csv")
    ap.add_argument("--raiz-frames", type=Path, default=RAIZ / "ml/data/processed/imt_coleta")
    ap.add_argument("--estacoes", type=Path, default=RAIZ / "ml/data/raw/estacoes/normalizado/cemaden_ped.csv")
    ap.add_argument("--modelo", type=Path, default=RAIZ / "backend/app/inference/modelos/intensidade.onnx")
    ap.add_argument("--dias", nargs="+", default=["2026-09-01", "2026-09-13", "2026-09-23"])
    ap.add_argument("--passo-s", type=float, default=10.0)
    ap.add_argument("--raio-km", type=float, default=5.0)
    ap.add_argument("--saida", type=Path, default=RAIZ / "ml/runs/correlacao_sessoes")
    args = ap.parse_args()

    m = pd.read_csv(args.manifest)
    m = m[m["lat"].notna()].copy()
    m["ts"] = pd.to_datetime(m["ts_utc"], utc=True)
    m["dia"] = m["ts"].dt.tz_convert("America/Sao_Paulo").dt.date.astype(str)
    m = m[m["dia"].isin(args.dias)].sort_values("ts")
    # 1 frame a cada passo_s por sessão (frames vizinhos a 1 fps são quase iguais)
    m = m[m.groupby("dia")["ts"].transform(lambda t: ((t - t.min()).dt.total_seconds() // args.passo_s)).diff().fillna(1) != 0]
    est = pd.read_csv(args.estacoes, parse_dates=["ts_utc"])
    frames = referencia(m, est, args.raio_km)
    frames = frames[frames["n_estacoes"] > 0]

    modelo = ModeloOnnx(args.modelo)
    p = modelo.probs([args.raiz_frames / r.pasta / r.arquivo for r in frames.itertuples()])
    frames = frames.assign(score=score_intensidade(p), p_garoa=p[:, 0], p_moderada=p[:, 1], p_forte=p[:, 2])

    args.saida.mkdir(parents=True, exist_ok=True)
    frames.drop(columns=["ts"]).to_csv(args.saida / "frames.csv", index=False)
    res = {"modelo": modelo.s.get_modelmeta().custom_metadata_map.get("experimento"), "raio_km": args.raio_km, "sessoes": {}}
    for nome, g in list(frames.groupby("dia")) + [("todas", frames)]:
        res["sessoes"][nome] = {
            "n_frames": int(len(g)),
            "mm_h_max_mediana": float(g["mm_h_mediana"].max()),
            "spearman_mediana_5km": spearman(g["score"], g["mm_h_mediana"]),
            "spearman_proxima": spearman(g["score"], g["mm_h_proxima"]),
        }
    faixas = []
    for lo, hi, rot in FAIXAS:
        g = frames[(frames["mm_h_mediana"] > lo) & (frames["mm_h_mediana"] <= hi)]
        if len(g):
            faixas.append({"mm_h": rot, "n": int(len(g)), "score_medio": float(g["score"].mean()),
                           "pred": g[["p_garoa", "p_moderada", "p_forte"]].values.argmax(1).tolist().count(0) / len(g)})
    res["score_por_faixa"] = faixas
    (args.saida / "resumo.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))

    print(f"modelo: {res['modelo']} | raio {args.raio_km} km")
    for nome, r in res["sessoes"].items():
        print(f"  {nome:11s} n={r['n_frames']:4d}  mm/h máx {r['mm_h_max_mediana']:5.1f}  "
              f"Spearman mediana {r['spearman_mediana_5km']:+.3f}  próxima {r['spearman_proxima']:+.3f}")
    print("  score médio por faixa de mm/h (mediana das estações):")
    for f in faixas:
        print(f"    {f['mm_h']:16s} n={f['n']:4d}  score {f['score_medio']:.2f}  (frac. prevista garoa {f['pred']:.2f})")


if __name__ == "__main__":
    main()
