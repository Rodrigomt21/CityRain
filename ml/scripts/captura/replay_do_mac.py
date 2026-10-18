#!/usr/bin/env python3
"""Replay do carro a partir do Mac (defesa), sem depender da Jetson ligada.

Reenvia uma sessão real gravada (jpg + json com GPS) para a API, em ordem, 1 frame a cada --intervalo s,
com captured_at = agora, a posição GPS original e ``metadata.demo`` (o painel mostra "REPLAY" e o
histórico ignora). Mesmo formato do ``uploader.py`` da Jetson. A API deduplica pelo sha256 da imagem
(retry da Jetson): cada envio recebe um comentário JPEG (FF FE) com o horário, que muda o hash sem
mexer em nenhum pixel, então ensaiar várias vezes é seguro.

Token: o do dispositivo da Jetson (``token`` em ml/scripts/captura/cityrain_config.json) ou
CITYRAIN_TOKEN. Nunca commitar o token.

Uso (da raiz do repositório):
    ml/.venv/bin/python ml/scripts/captura/replay_do_mac.py \
        --origem ml/data/processed/imt_coleta/cityrain_frames4 --padrao "frame_20260923_*.jpg" --intervalo 2
    # --api http://127.0.0.1:8010 para testar contra o backend local; --loop repete sem parar
"""
import argparse
import glob
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[3]
API_PADRAO = "https://api-production-046f.up.railway.app"


def token() -> str:
    if os.environ.get("CITYRAIN_TOKEN"):
        return os.environ["CITYRAIN_TOKEN"]
    return json.loads((RAIZ / "ml/scripts/captura/cityrain_config.json").read_text())["token"]


def uma_volta(frames, api, chave, intervalo, rotulo):
    cont = Counter()
    for i, f in enumerate(frames):
        g = json.load(open(f[:-4] + ".json"))["gps"]
        agora = datetime.now(timezone.utc).isoformat()
        meta = {"captured_at": agora, "latitude": g["latitude"], "longitude": g["longitude"], "source_type": "jetson_nano",
                "metadata": {"demo": rotulo, "frame_original": os.path.basename(f)}}
        jpg = open(f, "rb").read()
        com = f"cityrain demo {agora}".encode()
        jpg = jpg[:2] + b"\xff\xfe" + (len(com) + 2).to_bytes(2, "big") + com + jpg[2:]
        t = time.time()
        try:
            r = requests.post(f"{api}/api/v1/ingest", headers={"Authorization": f"Bearer {chave}"},
                              files={"image": (os.path.basename(f), jpg, "image/jpeg")},
                              data={"metadata": json.dumps(meta)}, timeout=60)
        except requests.RequestException as e:
            print(f"  #{i} sem rede: {e}", flush=True)
            continue
        if r.status_code not in (200, 201):
            print(f"  #{i} ERRO {r.status_code} {r.text[:120]}", flush=True)
            if r.status_code in (401, 403):
                raise SystemExit("token recusado")
            continue
        c = r.json()
        cont[c.get("weather_label")] += 1
        if i % 10 == 0:
            print(f"  #{i:3d} {c.get('weather_label')} {(c.get('confidence') or 0):.2f} ({g['latitude']:.4f},{g['longitude']:.4f})", flush=True)
        time.sleep(max(0, intervalo - (time.time() - t)))
    return cont


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--origem", default=str(RAIZ / "ml/data/processed/imt_coleta/cityrain_frames4"))
    ap.add_argument("--padrao", default="frame_20260923_*.jpg")
    ap.add_argument("--intervalo", type=float, default=2.0)
    ap.add_argument("--api", default=API_PADRAO)
    ap.add_argument("--rotulo", default="replay sessão 23/09/2026")
    ap.add_argument("--loop", action="store_true")
    a = ap.parse_args()
    frames = [f for f in sorted(glob.glob(os.path.join(a.origem, a.padrao)))
              if os.path.exists(f[:-4] + ".json") and (json.load(open(f[:-4] + ".json")).get("gps") or {}).get("fix")]
    if not frames:
        raise SystemExit("nenhum frame com GPS na origem")
    chave = token()
    print(f"[replay] {len(frames)} frames com GPS -> {a.api}, 1 a cada {a.intervalo}s", flush=True)
    while True:
        print(f"[replay] volta terminou: {dict(uma_volta(frames, a.api, chave, a.intervalo, a.rotulo))}", flush=True)
        if not a.loop:
            break


if __name__ == "__main__":
    main()
