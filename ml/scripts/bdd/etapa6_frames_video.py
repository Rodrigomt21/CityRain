"""Etapa 6: baixa (remotezip) os vídeos com radar moderada/forte e extrai um frame a cada 4 s.

O rótulo do frame é o do vídeo (radar em t0 = 10o s, janela de ±2 min cobre os 40 s). O frame vira
ambíguo se o vídeo já é ambíguo ou se o carro está a mais de 1 km do ponto de t0 (saiu da 3x3).
Retoma sozinho: vídeo com marcador .ok é pulado. Grava ml/data/manifests/bdd_mrms_frames.csv.

Uso (de dentro de ml/): .venv/bin/python scripts/bdd/etapa6_frames_video.py [manifesto] [saida]
    garoa de dia (amostra de vídeos inequívocos, para equilibrar a moderada no treino):
    .venv/bin/python scripts/bdd/etapa6_frames_video.py data/manifests/bdd_mrms.csv \
        data/manifests/bdd_mrms_garoa_frames.csv --classes garoa --so-dia --max-videos 300
"""
import argparse
import json, math, sys, tempfile, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import cv2, pandas as pd
from remotezip import RemoteZip
sys.path.insert(0, str(Path(__file__).parent))
from nucleo import gps_no_instante

D = Path("data/raw/public_datasets/bdd100k")
FR = D / "frames_video"; FR.mkdir(exist_ok=True)
URL = "http://dl.yf.io/bdd100k/bdd100k_videos.zip"
PASSO_S, RAIO_KM = 4, 1.0
_tl = threading.local()  # um RemoteZip por thread (o diretório central tem 100 mil entradas)


def _rz():
    if not hasattr(_tl, "rz"):
        _tl.rz = RemoteZip(URL, timeout=(30, 120))  # sem timeout uma conexão pendurada trava o lote
    return _tl.rz


def km(a, b):
    dy = (a[0] - b[0]) * 111.2
    dx = (a[1] - b[1]) * 111.2 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def extrair(r):
    ok = FR / f"{r.video}.ok"
    if ok.exists():
        return
    for tent in range(3):
        try:
            dados = _rz().read(f"bdd100k/videos/100k/{r.split}/{r.video}.mov")
            break
        except Exception as e:
            err = e
            _tl.__dict__.pop("rz", None)
    else:
        print("[erro]", r.video, err, flush=True); return
    with tempfile.NamedTemporaryFile(suffix=".mov") as f:
        f.write(dados); f.flush()
        cap = cv2.VideoCapture(f.name)
        for s in range(0, 40, PASSO_S):
            cap.set(cv2.CAP_PROP_POS_MSEC, s * 1000 + 500)
            lido, im = cap.read()
            if lido:
                cv2.imwrite(str(FR / f"{r.video}_{s:02d}.jpg"), im, [cv2.IMWRITE_JPEG_QUALITY, 92])
        cap.release()
    ok.touch()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifesto", nargs="?", default="data/manifests/bdd_mrms.csv")
    ap.add_argument("saida", nargs="?", default="data/manifests/bdd_mrms_frames.csv")
    ap.add_argument("--classes", nargs="+", default=["moderada", "forte"])
    ap.add_argument("--so-dia", action="store_true", help="só timeofday == daytime e vídeos inequívocos")
    ap.add_argument("--max-videos", type=int, help="amostra fixa (seed 0) de até N vídeos")
    a = ap.parse_args()
    MAN, OUT = Path(a.manifesto), Path(a.saida)
    df = pd.read_csv(MAN)
    alvo = df[df.classe.isin(a.classes)]
    if a.so_dia:
        alvo = alvo[(alvo.timeofday == "daytime") & (~alvo.ambiguo)]
    if a.max_videos and len(alvo) > a.max_videos:
        alvo = alvo.sample(a.max_videos, random_state=0)
    print(len(alvo), "vídeos", "/".join(a.classes) + ";", sum((FR / f"{v}.ok").exists() for v in alvo.video), "já feitos", flush=True)
    feitos = 0
    with ThreadPoolExecutor(6) as ex:
        for _ in ex.map(extrair, [r for r in alvo.itertuples()]):
            feitos += 1
            if feitos % 25 == 0:
                print(feitos, flush=True)

    linhas = []
    for r in alvo.itertuples():
        info = json.loads((D / "info_cache" / f"{r.video}.json").read_text())
        t_ini = info["startTime"]
        for s in range(0, 40, PASSO_S):
            img = FR / f"{r.video}_{s:02d}.jpg"
            if not img.exists():
                continue
            g = gps_no_instante(info.get("locations") or [], t_ini + s * 1000 + 500)
            dist = km((g[0], g[1]), (r.lat, r.lon)) if g else None
            amb, motivo = bool(r.ambiguo), r.motivo if isinstance(r.motivo, str) else ""
            if not amb and (dist is None or dist > RAIO_KM):
                amb, motivo = True, "fora_da_janela_1km"
            linhas.append(dict(imagem=img.name, video=r.video, seg=s, split=r.split, weather_bdd=r.weather_bdd,
                               timeofday=r.timeofday, utc_ms=t_ini + s * 1000, dist_t0_km=dist, mm_ponto=r.mm_ponto,
                               classe=r.classe, ambiguo=amb, motivo=motivo, grupo=r.video))
    out = pd.DataFrame(linhas)
    out.to_csv(OUT, index=False)
    print(len(out), "frames ->", OUT)
    print(pd.crosstab([out.classe, out.ambiguo], out.timeofday, margins=True))
    print("vídeos inequívocos por classe:", out[~out.ambiguo].groupby("classe").video.nunique().to_dict())


if __name__ == "__main__":
    main()
