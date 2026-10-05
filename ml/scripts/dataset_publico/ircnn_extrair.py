"""Extrai frames a 1 fps do irCNN (Yin et al. 2023) e gera manifest_ircnn.csv.

Alinhamento: o relogio de cada video vem da tag `creation_time` (UTC) + 8 h
(Hangzhou, UTC+8), confirmado contra o timestamp gravado no proprio frame.
Frame t (1 fps) => relogio local = inicio + t segundos. O pluviometro tem
1 leitura/min (unidade mm/min, resolucao 0,1 mm/min = 6 mm/h; Zheng et al.
2023, WRR) em hh:mm:45; assume-se que a leitura vale no instante do registro e
interpola-se linearmente entre leituras (Eq. 14 do paper). mm/h = mm/min * 60.
Frames fora da janela do pluviometro (sem dado) sao descartados.

Uso: python scripts/dataset_publico/ircnn_extrair.py [--sem-frames]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import subprocess
from pathlib import Path

import cv2
import numpy as np
import openpyxl

ML = Path(__file__).resolve().parents[2]
RAW = ML / "data/raw/public_datasets/ircnn"
OUT = ML / "data/processed/ircnn"
MANIFEST = ML / "data/manifests/manifest_ircnn.csv"
UTC8 = dt.timedelta(hours=8)
LIM_GAROA, LIM_FORTE, ZONA = 2.5, 10.0, 0.15
LARGURA = 960  # redimensiona 1920x1080 -> 960x540 (JPEG q90)


def classe(mm_h: float) -> str | None:
    """Classe do projeto; None na zona morta (+-15% de 2,5 e de 10)."""
    if mm_h <= 0:
        return "seco"
    for lim in (LIM_GAROA, LIM_FORTE):
        if abs(mm_h - lim) <= ZONA * lim:
            return None
    if mm_h <= LIM_GAROA:
        return "garoa"
    return "moderada" if mm_h <= LIM_FORTE else "forte"


def ler_pluviometro() -> dict[int, list[tuple[dt.datetime, float]]]:
    """Le o xlsx: {evento: [(datetime_local, mm/min)]}."""
    ws = openpyxl.load_workbook(RAW / "Gauge-observations.xlsx").active
    eventos: dict[int, list] = {}
    atual = 0
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[1] is None:
            continue
        if r[0]:
            atual = int(str(r[0]).split()[-1])
        hora = r[2]
        if isinstance(hora, dt.datetime):
            hora = hora.time()
        eventos.setdefault(atual, []).append((dt.datetime.combine(r[1].date(), hora), float(r[3])))
    return eventos


def inicio_video(path: Path) -> dt.datetime:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format_tags=creation_time", "-of", "csv=p=0", str(path)],
        text=True).strip()
    utc = dt.datetime.strptime(out[:19], "%Y-%m-%dT%H:%M:%S")
    return utc + UTC8


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sem-frames", action="store_true", help="so gera o manifest")
    args = ap.parse_args()
    linhas = []
    for ev, serie in sorted(ler_pluviometro().items()):
        video = RAW / f"Event {ev}.mp4"
        t0 = inicio_video(video)
        ts = np.array([(d - t0).total_seconds() for d, _ in serie])
        mmh = np.array([v for _, v in serie]) * 60.0
        periodo = "dia" if ev <= 6 else "noite"
        cap = cv2.VideoCapture(str(video))
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        pasta = OUT / f"event_{ev}"
        pasta.mkdir(parents=True, exist_ok=True)
        for t in range(n):
            ok = cap.grab()
            if not ok:
                break
            if t < ts[0] or t > ts[-1]:
                continue  # sem dado de pluviometro
            i = float(np.interp(t, ts, mmh))
            c = classe(i)
            if c is None:
                continue
            rel = f"data/processed/ircnn/event_{ev}/t{t:04d}.jpg"
            if not args.sem_frames:
                _, f = cap.retrieve()
                f = cv2.resize(f, (LARGURA, f.shape[0] * LARGURA // f.shape[1]), interpolation=cv2.INTER_AREA)
                cv2.imwrite(str(ML / rel), f, [cv2.IMWRITE_JPEG_QUALITY, 90])
            linhas.append({
                "caminho": rel, "classe": c, "mm_h": round(i, 3), "particao": "test_ircnn",
                "origem": "irCNN", "evento_id": f"ircnn__event_{ev}", "base_frame": "", "seed": "",
                "periodo": periodo, "t_video_s": t,
                "timestamp_local": (t0 + dt.timedelta(seconds=t)).isoformat(),
            })
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linhas[0]))
        w.writeheader()
        w.writerows(linhas)
    print(f"{len(linhas)} linhas -> {MANIFEST}")


if __name__ == "__main__":
    main()
