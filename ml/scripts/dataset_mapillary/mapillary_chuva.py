"""Fotos públicas do Mapillary tiradas NA CHUVA, achadas pelo radar MRMS (EUA).

Ninguém fotografa a rua de propósito num temporal conhecido (derecho de Houston: 0 de 6,35 mi), então
a busca é invertida:
  1. tiles de cobertura (z14) da área -> todas as fotos (id, sequência, captured_at, lon, lat, pano);
  2. por dia com foto, o acumulado de 24 h do MRMS (1 arquivo/dia) no lugar -> só dias >= LIMIAR_DIA_MM;
  3. para essas, PrecipRate de 2 min no instante (uma consulta por sequência x 2 min) -> classe pela
     regra do BDD (nucleo.decidir: ponto, 3x3, ±2 min).
Etapas com cache em data/raw/public_datasets/mapillary/<area>/ (retoma sozinho).

Uso (de dentro de ml/): .venv/bin/python scripts/dataset_mapillary/mapillary_chuva.py houston
"""
import gzip, json, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import mapbox_vector_tile as mvt, mercantile, numpy as np, pandas as pd, requests
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bdd"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dataset_youtube"))
from dashcam_radar import elevacao_sol
import mrms
from nucleo import url_mrms, timestamp_mrms_mais_proximo, decidir, mrms_valido

AREAS = {"houston": (-95.80, 29.60, -95.20, 30.05), "miami": (-80.45, 25.60, -80.10, 26.30),
         "tampa": (-82.75, 27.75, -82.25, 28.15), "nova_orleans": (-90.30, 29.85, -89.90, 30.10),
         "atlanta": (-84.60, 33.60, -84.20, 33.95),
         "orlando": (-81.55, 28.35, -81.20, 28.70), "jacksonville": (-81.85, 30.15, -81.45, 30.45),
         "dallas": (-97.00, 32.65, -96.60, 33.00), "kansas_city": (-94.75, 38.95, -94.45, 39.20),
         "chicago": (-87.85, 41.75, -87.55, 42.05), "charlotte": (-80.95, 35.10, -80.70, 35.35),
         "oklahoma_city": (-97.65, 35.35, -97.35, 35.60), "st_louis": (-90.40, 38.55, -90.15, 38.75),
         "jacksonville_amplo": (-82.00, 30.00, -81.30, 30.60), "tallahassee": (-84.40, 30.35, -84.15, 30.55),
         "gainesville": (-82.45, 29.58, -82.25, 29.75), "fort_lauderdale": (-80.35, 26.00, -80.05, 26.30),
         "west_palm": (-80.20, 26.55, -80.03, 26.85), "pensacola": (-87.35, 30.38, -87.10, 30.55),
         "mobile": (-88.25, 30.60, -88.00, 30.80), "baton_rouge": (-91.25, 30.35, -91.00, 30.55),
         "savannah": (-81.25, 31.95, -81.00, 32.15), "charleston": (-80.10, 32.70, -79.85, 32.95),
         "san_antonio": (-98.65, 29.35, -98.35, 29.60), "austin": (-97.90, 30.15, -97.60, 30.45),
         "washington": (-77.15, 38.80, -76.90, 39.00), "nova_york": (-74.05, 40.60, -73.75, 40.85)}
DESDE = datetime(2021, 1, 1, tzinfo=timezone.utc)  # QPE 24 h Pass2 do MRMS existe desde out/2020
LIMIAR_DIA_MM = 20.0
TOKEN = re.search(r"MAPILLARY_TOKEN=(\S+)", Path(".env").read_text()).group(1)


def tiles(area):
    """Etapa 1: fotos não-panorâmicas desde DESDE (cache por tile)."""
    D = Path(f"data/raw/public_datasets/mapillary/{area}/tiles"); D.mkdir(parents=True, exist_ok=True)
    def um(t):
        p = D / f"{t.x}_{t.y}.json"
        if p.exists():
            return json.loads(p.read_text())
        for _ in range(3):
            try:
                r = requests.get(f"https://tiles.mapillary.com/maps/vtp/mly1_public/2/{t.z}/{t.x}/{t.y}",
                                 params=dict(access_token=TOKEN), timeout=60)
                break
            except requests.RequestException:
                time.sleep(3)
        else:
            return []
        out = []
        if r.ok:
            b = mercantile.bounds(t)
            for f in mvt.decode(r.content).get("image", {}).get("features", []):
                q = f["properties"]
                if q.get("is_pano") or q.get("captured_at", 0) < DESDE.timestamp() * 1000:
                    continue
                x, y = f["geometry"]["coordinates"]  # 0..4096 dentro do tile
                out.append(dict(id=q["id"], seq=q.get("sequence_id"), t=q["captured_at"],
                                lon=b.west + (b.east - b.west) * x / 4096, lat=b.south + (b.north - b.south) * y / 4096))
        p.write_text(json.dumps(out))
        return out
    ts = list(mercantile.tiles(*AREAS[area], 14))
    with ThreadPoolExecutor(8) as ex:
        fotos = [f for lst in ex.map(um, ts) for f in lst]
    return pd.DataFrame(fotos)


def qpe24(dia_utc12):
    """Acumulado 24 h (mm) terminando às 12 UTC do dia; cache em disco."""
    D = Path("data/raw/public_datasets/mapillary/qpe24"); D.mkdir(parents=True, exist_ok=True)
    p = D / f"{dia_utc12:%Y%m%d}.npy"
    if p.exists():
        return np.load(p)
    url = ("https://mtarchive.geol.iastate.edu/%s/mrms/ncep/MultiSensor_QPE_24H_Pass2/"
           "MultiSensor_QPE_24H_Pass2_00.00_%s-120000.grib2.gz" % (dia_utc12.strftime("%Y/%m/%d"), dia_utc12.strftime("%Y%m%d")))
    b = mrms.baixar(url)
    if b is None:
        return None
    v = mrms.campo(b).astype("float16")
    np.save(p, v)
    return v


def main():
    area = sys.argv[1] if len(sys.argv) > 1 else "houston"
    D = Path(f"data/raw/public_datasets/mapillary/{area}")
    df = tiles(area)
    print(len(df), "fotos (sem panorâmica) desde", DESDE.date(), flush=True)
    df["utc"] = pd.to_datetime(df.t, unit="ms", utc=True)
    # janela de 24 h do QPE termina às 12 UTC: foto antes das 12 UTC conta no arquivo do mesmo dia
    df["dia12"] = (df.utc + pd.Timedelta(hours=12)).dt.floor("D")
    ij = [mrms.indice(a, o) for a, o in zip(df.lat, df.lon)]
    df["i"], df["j"] = [x[0] for x in ij], [x[1] for x in ij]
    dias = sorted(df.dia12.unique())
    print(len(dias), "dias com foto -> QPE 24 h", flush=True)
    acum = np.full(len(df), np.nan)
    with ThreadPoolExecutor(6) as ex:
        campos = dict(zip(dias, ex.map(lambda d: qpe24(pd.Timestamp(d).to_pydatetime()), dias)))
    for d, v in campos.items():
        if v is not None:
            m = (df.dia12 == d).values
            acum[m] = v[df.i.values[m], df.j.values[m]]
    df["mm_24h"] = acum
    cand = df[df.mm_24h >= LIMIAR_DIA_MM].copy()
    print(len(cand), f"fotos em dias com >= {LIMIAR_DIA_MM} mm no local", flush=True)
    cand["ts0"] = [timestamp_mrms_mais_proximo(t.to_pydatetime()) for t in cand.utc]
    cache = {}
    def campo(ts):
        if ts not in cache:
            b = mrms.baixar(url_mrms(ts)); cache[ts] = mrms.campo(b) if b is not None else None
        return cache[ts]
    precisos = sorted({ts + timedelta(minutes=o) for ts in cand.ts0 for o in (-2, 0, 2)})
    print(len(precisos), "arquivos PrecipRate de 2 min", flush=True)
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(campo, precisos))
    lin = []
    for r in cand.itertuples():
        v = campo(r.ts0)
        if v is None:
            continue
        viz = [mrms_valido(x) for x in v[r.i - 1:r.i + 2, r.j - 1:r.j + 2].ravel()]
        t2 = [mrms_valido(campo(r.ts0 + timedelta(minutes=o))[r.i, r.j]) if campo(r.ts0 + timedelta(minutes=o)) is not None else None
              for o in (-2, 2)]
        c, amb, mot = decidir(mrms_valido(v[r.i, r.j]), viz, t2, [None, None])
        lin.append(dict(id=r.id, seq=r.seq, utc=r.utc.isoformat(), lat=r.lat, lon=r.lon, mm_24h=r.mm_24h,
                        dia=elevacao_sol(r.lat, r.lon, r.utc.to_pydatetime()) > 0,
                        mm_h=mrms_valido(v[r.i, r.j]), classe=c, ambiguo=amb, motivo=mot))
    out = pd.DataFrame(lin)
    out.to_csv(D / "candidatas.csv", index=False)
    print(pd.crosstab([out.dia, out.classe], out.ambiguo))
    # ATENÇÃO: o captured_at do Mapillary pode estar errado (Houston: câmera mostrava 21/07, Mapillary 05/08).
    # Conferir num painel o relógio gravado na imagem antes de usar uma sequência.
    print("sequências de DIA com forte inequívoco:", out[(out.classe == "forte") & ~out.ambiguo & out.dia].seq.nunique())


if __name__ == "__main__":
    main()
