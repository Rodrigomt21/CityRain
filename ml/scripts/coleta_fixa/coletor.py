#!/usr/bin/env python3
"""Coletor de câmeras FIXAS para popular o dataset (qualquer dispositivo, 04/10/2026).

O gargalo do CityRain é evento de chuva rotulado, não imagem. Uma câmera parada
perto de um pluviômetro pega TODO temporal que passar por ela, sem ninguém
dirigir. Este coletor tira um frame a cada ``intervalo_s`` de cada fonte e grava
no MESMO contrato da Jetson (``frame_AAAAMMDD_HHMMSS_mmm.jpg`` + ``.json`` com
``capturado_em_utc`` e ``gps``), então ``ml/scripts/rotulagem/gerar_manifest.py``
rotula pela estação mais próxima sem mudança nenhuma.

Tipos de fonte (``fontes:`` no YAML):

- ``youtube``  — live 24 h (praia, avenida, prédio). Resolve o HLS com yt-dlp e
  extrai 1 frame com ffmpeg. A URL do HLS expira; é renovada a cada 30 min.
- ``snapshot`` — URL que devolve um JPEG (ex.: app "IP Webcam" num celular
  velho na janela: ``http://<ip-do-celular>:8080/shot.jpg``; câmera IP).
- ``camera``   — webcam/USB local pelo índice do OpenCV (notebook, Jetson).

Posição: câmera fixa tem posição conhecida e permanente. O JSON leva
``gps.ultimo_fix_em = capturado_em_utc`` (fix "sempre fresco") e ``gps.fixo =
true`` para a rotulagem não descartar o frame por GPS velho.

Frames idênticos ao anterior da mesma fonte (stream congelado, câmera offline
mostrando a mesma imagem) são descartados por hash.

Uso:
    ml/.venv/bin/python ml/scripts/coleta_fixa/coletor.py ml/configs/coleta_fixa.yaml
    ml/.venv/bin/python ml/scripts/coleta_fixa/coletor.py ml/configs/coleta_fixa.yaml --uma-rodada
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[3]
RENOVAR_HLS_S = 30 * 60
TIMEOUT_S = 40


@dataclass
class Fonte:
    id: str
    tipo: str
    lat: float
    lon: float
    url: str = ""
    indice: int = 0
    intervalo_s: float = 60.0
    descricao: str = ""
    # estado em execução
    proxima: float = 0.0
    ultimo_hash: str = ""
    hls: str = ""
    hls_em: float = 0.0
    falhas: int = 0
    extras: dict = field(default_factory=dict)


def carregar_fontes(cfg: dict) -> list[Fonte]:
    padrao = float(cfg.get("intervalo_s", 60))
    fontes = []
    for f in cfg["fontes"]:
        if not f.get("ativa", True):
            continue
        if f["tipo"] not in ("youtube", "snapshot", "camera"):
            raise ValueError(f"{f['id']}: tipo desconhecido {f['tipo']!r}")
        fontes.append(Fonte(
            id=f["id"], tipo=f["tipo"], lat=float(f["lat"]), lon=float(f["lon"]),
            url=f.get("url", ""), indice=int(f.get("indice", 0)),
            intervalo_s=float(f.get("intervalo_s", padrao)), descricao=f.get("descricao", ""),
        ))
    ids = [f.id for f in fontes]
    if len(ids) != len(set(ids)):
        raise ValueError("ids de fonte repetidos")
    return fontes


# ------------------------------------------------------------------ captura
def _jpeg_youtube(fonte: Fonte) -> bytes:
    agora = time.time()
    if not fonte.hls or agora - fonte.hls_em > RENOVAR_HLS_S:
        r = subprocess.run(["yt-dlp", "-g", "-f", "b[height<=720]/bv*[height<=720]/b/bv*", fonte.url],
                           capture_output=True, text=True, timeout=TIMEOUT_S)
        if r.returncode != 0 or not r.stdout.strip():
            raise RuntimeError(f"yt-dlp: {r.stderr.strip()[-200:]}")
        fonte.hls, fonte.hls_em = r.stdout.strip().splitlines()[0], agora
    with tempfile.NamedTemporaryFile(suffix=".jpg") as tmp:
        r = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", fonte.hls, "-frames:v", "1",
                            "-q:v", "2", tmp.name], capture_output=True, text=True, timeout=TIMEOUT_S)
        if r.returncode != 0:
            fonte.hls = ""  # força renovar na próxima
            raise RuntimeError(f"ffmpeg: {r.stderr.strip()[-200:]}")
        return Path(tmp.name).read_bytes()


def _jpeg_snapshot(fonte: Fonte) -> bytes:
    req = urllib.request.Request(fonte.url, headers={"User-Agent": "CityRain-coletor/1.0 (pesquisa TCC IMT)"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        dados = r.read()
    if not dados.startswith(b"\xff\xd8"):
        raise RuntimeError("resposta não é JPEG")
    return dados


def _jpeg_camera(fonte: Fonte) -> bytes:
    import cv2

    cap = cv2.VideoCapture(fonte.indice)
    try:
        for _ in range(5):  # descarta frames do buffer/auto-exposição
            ok, frame = cap.read()
        if not ok:
            raise RuntimeError(f"câmera {fonte.indice} não entregou frame")
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
        return buf.tobytes()
    finally:
        cap.release()


CAPTURAS = {"youtube": _jpeg_youtube, "snapshot": _jpeg_snapshot, "camera": _jpeg_camera}


# ------------------------------------------------------------------ gravação
def gravar_frame(dados: bytes, fonte: Fonte, destino: Path, quando: datetime) -> Path | None:
    """Grava o par jpg+json no contrato da Jetson; None se for repetido."""
    h = hashlib.sha256(dados).hexdigest()
    if h == fonte.ultimo_hash:
        return None
    fonte.ultimo_hash = h
    pasta = destino / fonte.id
    pasta.mkdir(parents=True, exist_ok=True)
    nome = f"frame_{quando:%Y%m%d_%H%M%S}_{quando.microsecond // 1000:03d}"
    jpg, js = pasta / f"{nome}.jpg", pasta / f"{nome}.json"
    iso = quando.isoformat()
    meta = {
        "schema": 2,
        "device_id": fonte.id,
        "capturado_em_utc": iso,
        "arquivo": jpg.name,
        "gps": {"latitude": fonte.lat, "longitude": fonte.lon, "ultimo_fix_em": iso, "fixo": True},
        "fonte": {"tipo": fonte.tipo, "url": fonte.url, "descricao": fonte.descricao, "sha256": h},
    }
    # mesma ordem da Jetson: o .json só existe depois do .jpg completo
    for caminho, conteudo in ((jpg, dados), (js, json.dumps(meta, ensure_ascii=False).encode())):
        tmp = caminho.with_suffix(caminho.suffix + ".tmp")
        tmp.write_bytes(conteudo)
        os.replace(tmp, caminho)
    return jpg


def rodada(fontes: list[Fonte], destino: Path, forcar: bool = False) -> None:
    agora = time.time()
    for f in fontes:
        if not forcar and agora < f.proxima:
            continue
        quando = datetime.now(timezone.utc)
        try:
            caminho = gravar_frame(CAPTURAS[f.tipo](f), f, destino, quando)
            f.falhas = 0
            f.proxima = agora + f.intervalo_s
            estado = caminho.name if caminho else "repetido (descartado)"
        except Exception as e:  # noqa: BLE001 — uma fonte fora do ar não para as outras
            f.falhas += 1
            f.proxima = agora + min(f.intervalo_s * 2 ** f.falhas, 1800)  # backoff até 30 min
            estado = f"FALHA {f.falhas}: {e}"
        print(f"[{quando:%Y-%m-%d %H:%M:%S}Z] {f.id}: {estado}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config", type=Path)
    ap.add_argument("--uma-rodada", action="store_true", help="captura 1 frame de cada fonte e sai")
    args = ap.parse_args()
    cfg = yaml.safe_load(args.config.read_text())
    destino = RAIZ / cfg.get("destino", "ml/data/raw/coleta_fixa")
    fontes = carregar_fontes(cfg)
    print(f"[coletor] {len(fontes)} fontes -> {destino.relative_to(RAIZ)}", flush=True)
    if args.uma_rodada:
        rodada(fontes, destino, forcar=True)
        return
    while True:
        rodada(fontes, destino)
        time.sleep(1)


if __name__ == "__main__":
    sys.exit(main())
