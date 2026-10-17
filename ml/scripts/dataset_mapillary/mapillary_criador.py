"""Fotos do Mapillary de UM usuário tiradas na chuva (radar MRMS), em qualquer lugar dos EUA.

Quem já apareceu dirigindo num temporal (ex.: 'allen', BlackVue em Jacksonville, 27/07/2024) costuma
dirigir na chuva outras vezes. Busca por usuário em vez de por área:
  1. por dia desde DESDE: 1 foto (limit=1) -> dia tem foto? onde?
  2. QPE 24 h do MRMS nesse ponto -> só dias >= LIMIAR_DIA_MM;
  3. nesses dias, todas as fotos (janelas de 1 h, até 2000 cada) -> regra do BDD (mapillary_chuva).
Saída: data/raw/public_datasets/mapillary/criador_<usuario>/candidatas.csv (mesmo formato de mapillary_chuva.py).

Uso (de dentro de ml/): .venv/bin/python scripts/dataset_mapillary/mapillary_criador.py allen
"""
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np, pandas as pd, requests
from mapillary_chuva import DESDE, LIMIAR_DIA_MM, TOKEN, qpe24, elevacao_sol, mrms, url_mrms, \
    timestamp_mrms_mais_proximo, decidir, mrms_valido

API = "https://graph.mapillary.com/images"


def consulta(usuario, ini, fim, limit):
    for _ in range(3):
        try:
            r = requests.get(API, timeout=120, params=dict(
                access_token=TOKEN, creator_username=usuario, fields="id,captured_at,geometry,sequence", limit=limit,
                start_captured_at=ini.strftime("%Y-%m-%dT%H:%M:%SZ"), end_captured_at=fim.strftime("%Y-%m-%dT%H:%M:%SZ")))
            if r.ok:
                return [dict(id=f["id"], seq=f.get("sequence"), t=f["captured_at"], lon=f["geometry"]["coordinates"][0],
                             lat=f["geometry"]["coordinates"][1]) for f in r.json().get("data", [])]
        except requests.RequestException:
            pass
    return []


def main():
    usuario = sys.argv[1]
    D = Path(f"data/raw/public_datasets/mapillary/criador_{usuario}"); D.mkdir(parents=True, exist_ok=True)
    hoje = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    dias = [DESDE + timedelta(days=k) for k in range((hoje - DESDE).days)]
    cache_dias = D / "dias.csv"
    if cache_dias.exists():
        amostra = pd.read_csv(cache_dias)
    else:
        with ThreadPoolExecutor(8) as ex:
            r = list(ex.map(lambda d: consulta(usuario, d, d + timedelta(days=1), 1), dias))
        amostra = pd.DataFrame([x[0] | dict(dia=d.strftime("%Y-%m-%d")) for d, x in zip(dias, r) if x])
        amostra.to_csv(cache_dias, index=False)
    print(len(amostra), "dias com foto", flush=True)
    # janela do QPE termina às 12 UTC: foto antes das 12 UTC conta no arquivo do mesmo dia; olha os dois
    def acum(r):
        i, j = mrms.indice(r.lat, r.lon)
        d = datetime.strptime(r.dia, "%Y-%m-%d")
        vs = [qpe24(d), qpe24(d + timedelta(days=1))]
        return max(float(v[i, j]) for v in vs if v is not None) if any(v is not None for v in vs) else np.nan
    with ThreadPoolExecutor(6) as ex:
        amostra["mm_24h"] = list(ex.map(acum, amostra.itertuples()))
    chuva = amostra[amostra.mm_24h >= LIMIAR_DIA_MM]
    print(len(chuva), f"dias com >= {LIMIAR_DIA_MM} mm no ponto da 1a foto", flush=True)
    jan = [datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(hours=h)
           for d in chuva.dia for h in range(24)]
    with ThreadPoolExecutor(8) as ex:
        fotos = pd.DataFrame([f for lst in ex.map(lambda t: consulta(usuario, t, t + timedelta(hours=1), 2000), jan)
                              for f in lst]).drop_duplicates("id")
    fotos["utc"] = pd.to_datetime(fotos.t, unit="ms", utc=True)
    fotos["dia"] = [elevacao_sol(a, o, t.to_pydatetime()) > 0 for a, o, t in zip(fotos.lat, fotos.lon, fotos.utc)]
    fotos = fotos[fotos.dia].copy()
    print(len(fotos), "fotos de dia nesses dias", flush=True)
    fotos["ts0"] = [timestamp_mrms_mais_proximo(t.to_pydatetime()) for t in fotos.utc]
    fotos.to_csv(D / "fotos_dia.csv", index=False)
    # campos de 2 min têm ~100 MB cada: blocos de BLOCO instantes, baixados em paralelo e descartados depois
    BLOCO = 40
    def campo(ts):
        b = mrms.baixar(url_mrms(ts))
        return ts, (mrms.campo(b) if b is not None else None)
    lin = []
    instantes = sorted(fotos.ts0.unique())
    for k in range(0, len(instantes), BLOCO):
        bloco = instantes[k:k + BLOCO]
        precisa = sorted({ts + timedelta(minutes=o) for ts in bloco for o in (-2, 0, 2)})
        with ThreadPoolExecutor(8) as ex:
            cache = dict(ex.map(campo, precisa))
        for r in fotos[fotos.ts0.isin(bloco)].itertuples():
            v = cache[r.ts0]
            if v is None:
                continue
            i, j = mrms.indice(r.lat, r.lon)
            viz = [mrms_valido(x) for x in v[i - 1:i + 2, j - 1:j + 2].ravel()]
            t2 = [mrms_valido(cache[r.ts0 + timedelta(minutes=o)][i, j]) if cache[r.ts0 + timedelta(minutes=o)] is not None
                  else None for o in (-2, 2)]
            c, amb, mot = decidir(mrms_valido(v[i, j]), viz, t2, [None, None])
            lin.append(dict(id=r.id, seq=r.seq, utc=r.utc.isoformat(), lat=r.lat, lon=r.lon, mm_24h=np.nan, dia=True,
                            mm_h=mrms_valido(v[i, j]), classe=c, ambiguo=amb, motivo=mot))
        del cache
        print(f"{min(k + BLOCO, len(instantes))}/{len(instantes)} instantes", flush=True)
    out = pd.DataFrame(lin)
    out.to_csv(D / "candidatas.csv", index=False)
    ok = out[~out.ambiguo]
    print(pd.crosstab(ok.utc.str[:10], ok.classe))


if __name__ == "__main__":
    main()
