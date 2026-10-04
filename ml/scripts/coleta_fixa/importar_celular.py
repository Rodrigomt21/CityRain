#!/usr/bin/env python3
"""Importa fotos e vídeos de celular para o contrato de frames da Jetson.

Qualquer pessoa filma/fotografa a chuva com o GPS do celular ligado; este script
lê posição e horário do PRÓPRIO arquivo e grava ``frame_*.jpg`` + ``.json`` em
``ml/data/raw/celular/<pessoa>/``, prontos para ``gerar_manifest.py`` rotular
pela estação mais próxima.

- Foto (JPEG/HEIC convertido): EXIF ``GPSInfo`` + ``DateTimeOriginal`` com
  ``OffsetTimeOriginal`` (se faltar o offset, assume ``--fuso``, padrão -03:00).
- Vídeo (MP4/MOV): ``ffprobe`` lê ``creation_time`` (UTC) e ``location``
  (ISO 6709, ex. ``-23.5505-046.6333/``); extrai 1 frame a cada ``--passo-s``
  segundos com o instante = início + offset.

Arquivo sem GPS ou sem horário é PULADO e listado — nunca se inventa posição.

Uso:
    ml/.venv/bin/python ml/scripts/coleta_fixa/importar_celular.py ~/Downloads/chuva_04-10 --pessoa rodrigo
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image
from PIL.ExifTags import GPSTAGS, TAGS

RAIZ = Path(__file__).resolve().parents[3]
FOTOS = {".jpg", ".jpeg"}
VIDEOS = {".mp4", ".mov", ".m4v"}
_ISO6709 = re.compile(r"([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)")


def _graus(v, ref: str) -> float:
    g, m, s = (float(x) for x in v)
    d = g + m / 60 + s / 3600
    return -d if ref in ("S", "W") else d


def _fuso(texto: str) -> timezone:
    sinal = -1 if texto.startswith("-") else 1
    h, m = texto.lstrip("+-").split(":")
    return timezone(sinal * timedelta(hours=int(h), minutes=int(m)))


def ler_foto(caminho: Path, fuso_padrao: str) -> tuple[float, float, datetime] | None:
    exif = Image.open(caminho).getexif()
    gps_raw = exif.get_ifd(0x8825)
    gps = {GPSTAGS.get(k, k): v for k, v in gps_raw.items()}
    sub = {TAGS.get(k, k): v for k, v in exif.get_ifd(0x8769).items()}
    if "GPSLatitude" not in gps or "DateTimeOriginal" not in sub:
        return None
    lat = _graus(gps["GPSLatitude"], gps.get("GPSLatitudeRef", "N"))
    lon = _graus(gps["GPSLongitude"], gps.get("GPSLongitudeRef", "E"))
    local = datetime.strptime(sub["DateTimeOriginal"], "%Y:%m:%d %H:%M:%S")
    quando = local.replace(tzinfo=_fuso(sub.get("OffsetTimeOriginal") or fuso_padrao))
    return lat, lon, quando.astimezone(timezone.utc)


def ler_video(caminho: Path) -> tuple[float, float, datetime, float] | None:
    r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(caminho)],
                       capture_output=True, text=True)
    fmt = json.loads(r.stdout or "{}").get("format", {})
    tags = {k.lower(): v for k, v in fmt.get("tags", {}).items()}
    loc = tags.get("location") or tags.get("com.apple.quicktime.location.iso6709")
    t = tags.get("creation_time") or tags.get("com.apple.quicktime.creationdate")
    m = _ISO6709.match(loc or "")
    if not m or not t:
        return None
    # alguns muxers repetem a tag ("a;b"); vale a primeira
    quando = datetime.fromisoformat(t.split(";")[0].strip().replace("Z", "+00:00")).astimezone(timezone.utc)
    return float(m.group(1)), float(m.group(2)), quando, float(fmt.get("duration", 0))


def gravar(jpg_bytes: bytes, lat: float, lon: float, quando: datetime, pasta: Path, origem: str) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    nome = f"frame_{quando:%Y%m%d_%H%M%S}_{quando.microsecond // 1000:03d}"
    jpg = pasta / f"{nome}.jpg"
    iso = quando.isoformat()
    meta = {
        "schema": 2,
        "device_id": f"celular_{pasta.name}",
        "capturado_em_utc": iso,
        "arquivo": jpg.name,
        "gps": {"latitude": lat, "longitude": lon, "ultimo_fix_em": iso},
        "fonte": {"tipo": "celular", "arquivo_original": origem},
    }
    for caminho, conteudo in ((jpg, jpg_bytes), (jpg.with_suffix(".json"), json.dumps(meta, ensure_ascii=False).encode())):
        tmp = caminho.with_suffix(caminho.suffix + ".tmp")
        tmp.write_bytes(conteudo)
        os.replace(tmp, caminho)
    return jpg


def importar(entrada: Path, pasta: Path, fuso: str, passo_s: float) -> dict[str, list[str]]:
    rel = {"importados": [], "pulados_sem_gps_ou_hora": []}
    for arq in sorted(p for p in entrada.rglob("*") if p.suffix.lower() in FOTOS | VIDEOS):
        if arq.suffix.lower() in FOTOS:
            info = ler_foto(arq, fuso)
            if info is None:
                rel["pulados_sem_gps_ou_hora"].append(arq.name)
                continue
            lat, lon, quando = info
            rel["importados"].append(gravar(arq.read_bytes(), lat, lon, quando, pasta, arq.name).name)
            continue
        info = ler_video(arq)
        if info is None:
            rel["pulados_sem_gps_ou_hora"].append(arq.name)
            continue
        lat, lon, inicio, duracao = info
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(arq), "-vf", f"fps=1/{passo_s}",
                            "-q:v", "2", f"{tmp}/q_%05d.jpg"], check=True)
            for i, q in enumerate(sorted(Path(tmp).glob("q_*.jpg"))):
                quando = inicio + timedelta(seconds=i * passo_s)
                rel["importados"].append(gravar(q.read_bytes(), lat, lon, quando, pasta, f"{arq.name}@{i * passo_s:.0f}s").name)
    return rel


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrada", type=Path, help="pasta com fotos/vídeos do celular")
    ap.add_argument("--pessoa", required=True, help="subpasta de destino (quem filmou)")
    ap.add_argument("--fuso", default="-03:00", help="offset quando a foto não traz OffsetTimeOriginal")
    ap.add_argument("--passo-s", type=float, default=2.0, help="1 frame a cada N s de vídeo")
    args = ap.parse_args()
    pasta = RAIZ / "ml/data/raw/celular" / args.pessoa
    rel = importar(args.entrada.expanduser(), pasta, args.fuso, args.passo_s)
    print(f"{len(rel['importados'])} frames em {pasta.relative_to(RAIZ)}")
    if rel["pulados_sem_gps_ou_hora"]:
        print(f"{len(rel['pulados_sem_gps_ou_hora'])} arquivos sem GPS/horário (ligue a localização da câmera):")
        for n in rel["pulados_sem_gps_ou_hora"][:20]:
            print("  -", n)


if __name__ == "__main__":
    main()
