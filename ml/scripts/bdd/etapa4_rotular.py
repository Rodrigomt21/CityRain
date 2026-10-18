"""Etapa 4: aplica limiares + regra de ambiguidade e grava ml/data/manifests/bdd_mrms.csv."""
import json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from nucleo import decidir, mrms_valido

D = Path("data/raw/public_datasets/bdd100k")
OUT = Path("data/manifests/bdd_mrms.csv")


def main():
    est = json.loads((D / "mrms_janelas.json").read_text())
    amostras = [r for r in json.loads((D / "selecao_gps.json").read_text()) if "lat" in r and "ts0" not in r or "lat" in r]
    linhas = []
    for a in amostras:
        if a.get("timelapse"):
            continue
        t0 = datetime.fromtimestamp(a["utc_ms"] / 1000, timezone.utc)
        from nucleo import timestamp_mrms_mais_proximo
        ts0 = timestamp_mrms_mais_proximo(t0)

        def w(off):
            d = est.get((ts0 + timedelta(minutes=off)).isoformat())
            if not isinstance(d, dict):
                return None
            return d.get(a["name"])

        w0 = w(0)
        base = dict(imagem=a["name"] + ".jpg", video=a["name"], split=a["split"], weather_bdd=a["weather"],
                    scene=a["scene"], timeofday=a["timeofday"], lat=round(a["lat"], 6), lon=round(a["lon"], 6),
                    utc=t0.strftime("%Y-%m-%dT%H:%M:%SZ"), mrms_ts=ts0.strftime("%Y%m%dT%H%MZ"))
        if w0 is None:
            linhas.append({**base, "classe": "", "ambiguo": True, "motivo": "sem_dado_mrms"}); continue
        viz = [mrms_valido(x) for x in w0]
        ponto = viz[4]
        validos = [v for v in viz if v is not None]

        def pt(off):
            x = w(off)
            return None if x is None else mrms_valido(x[4])

        def mx(off):
            x = w(off)
            if x is None:
                return None
            v = [mrms_valido(i) for i in x]; v = [i for i in v if i is not None]
            return max(v) if v else None

        m2, p2, m4, p4 = pt(-2), pt(2), pt(-4), pt(4)
        ext = [mx(-6), mx(6), mx(-10), mx(10)]
        classe, amb, motivo = decidir(ponto, viz, [m2, p2], [m4, p4], [e for e in ext if e is not None])
        if classe == "seco" and not amb and any(e is None for e in ext):
            amb, motivo = True, "seco_sem_janela_10min"
        linhas.append({**base, "mm_ponto": ponto, "mm_mediana3x3": float(np.median(validos)) if validos else None,
                       "mm_max3x3": max(validos) if validos else None,
                       "mm_m2": m2, "mm_p2": p2, "mm_m4": m4, "mm_p4": p4,
                       "mm_max_pm6_pm10": max([e for e in ext if e is not None], default=None),
                       "classe": classe or "", "ambiguo": amb, "motivo": motivo})
    df = pd.DataFrame(linhas)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(len(df), "linhas ->", OUT)
    df["conj"] = np.where(df.weather_bdd == "rainy", "rainy", "clear")
    df["periodo"] = df.timeofday.map({"daytime": "dia", "night": "noite"}).fillna("amanhecer/entardecer")
    for conj, g in df.groupby("conj"):
        print(f"\n=== {conj}: total {len(g)}")
        print(pd.crosstab(g.classe.replace("", "(sem dado)"), g.periodo, margins=True))
        gu = g[~g.ambiguo]
        print(f"-- inequívocas: {len(gu)}")
        print(pd.crosstab(gu.classe, gu.periodo, margins=True))
        print(g[g.ambiguo].motivo.value_counts().to_string())


if __name__ == "__main__":
    main()
