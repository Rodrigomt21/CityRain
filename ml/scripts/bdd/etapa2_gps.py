"""Etapa 2: baixa só os JSONs de info necessários (remotezip) e extrai tempo/posição do 10o s."""
import json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from remotezip import RemoteZip
sys.path.insert(0, str(Path(__file__).parent))
from nucleo import gps_no_instante, FRAME_MS

D = Path("data/raw/public_datasets/bdd100k")
URL = "http://dl.yf.io/bdd100k/bdd100k_info.zip"
CACHE = D / "info_cache"; CACHE.mkdir(exist_ok=True)


import threading
_tl = threading.local()


def _rz():
    if not hasattr(_tl, "rz"):
        _tl.rz = RemoteZip(URL)
    return _tl.rz


def obter(r):
    out = CACHE / f"{r['name']}.json"
    if out.exists():
        return json.loads(out.read_text())
    for tent in range(3):
        try:
            j = json.loads(_rz().read(f"100k/{r['split']}/{r['name']}.json"))
            # guarda só o essencial (gyro/accel pesam 99%)
            red = {k: j.get(k) for k in ("startTime", "endTime", "rideID", "timelapse", "locations")}
            out.write_text(json.dumps(red))
            return red
        except Exception as e:
            err = e
            _tl.__dict__.pop('rz', None)
    return {"erro": str(err)}


def main():
    sel = json.loads((D / "selecao.json").read_text())
    with ThreadPoolExecutor(8) as ex:
        infos = list(ex.map(obter, sel))
    res = []
    for r, i in zip(sel, infos):
        if "erro" in i or not i.get("startTime"):
            r["motivo_descarte"] = "info_indisponivel"; res.append(r); continue
        alvo = i["startTime"] + FRAME_MS
        g = gps_no_instante(i.get("locations") or [], alvo)
        r.update(video=r["name"], utc_ms=alvo, timelapse=i.get("timelapse"))
        if g is None:
            r["motivo_descarte"] = "sem_gps"
        else:
            r.update(lat=g[0], lon=g[1], speed=g[2])
        res.append(r)
    (D / "selecao_gps.json").write_text(json.dumps(res))
    from collections import Counter
    print(Counter(r.get("motivo_descarte", "ok") for r in res))


if __name__ == "__main__":
    main()
