#!/usr/bin/env python3
"""Replay de uma chuva real gravada por uma câmera fixa, pelo pipeline de produção (spec CF8).

Cada frame do evento é reenviado ao POST /api/v1/ingest como se fosse agora, com
`metadata.demo` (o histórico exclui demo). O backend deduplica por sha256 da imagem,
então cada envio ganha um comentário JPEG com a hora do replay: os pixels são os
mesmos, o hash não, e o replay pode ser ensaiado quantas vezes for preciso.

Uso:
    ml/.venv/bin/python ml/scripts/coleta_fixa/replay_evento.py --camera bc_atlantica \
        --de 2026-10-01T18:00:00-03:00 --ate 2026-10-01T19:00:00-03:00 --intervalo 2
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from coletor import enviar_frame, token_da_fonte  # noqa: E402


def com_marca_de_replay(jpeg: bytes, marca: str) -> bytes:
    """Insere um segmento COM logo após o SOI; não toca nos dados da imagem."""
    if not jpeg.startswith(b"\xff\xd8"):
        raise ValueError("não é JPEG")
    texto = f"cityrain-replay:{marca}".encode()
    seg = b"\xff\xfe" + (len(texto) + 2).to_bytes(2, "big") + texto
    return jpeg[:2] + seg + jpeg[2:]


def _quando(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def selecionar_frames(manifest: Path, camera: str, de: datetime | None, ate: datetime | None, raiz_frames: Path) -> list[Path]:
    with open(manifest, newline="") as f:
        linhas = [r for r in csv.DictReader(f) if r["pasta"] == camera]
    escolhidos = []
    for r in sorted(linhas, key=lambda r: r["ts_utc"]):
        t = _quando(r["ts_utc"])
        if (de and t < de) or (ate and t > ate):
            continue
        p = raiz_frames / camera / r["arquivo"]
        if p.is_file() and p.with_suffix(".json").is_file():
            escolhidos.append(p)
    return escolhidos


def preparar_frame_replay(jpg: Path, destino: Path, agora: datetime, marca: str) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    meta = json.loads(jpg.with_suffix(".json").read_text())
    meta["capturado_originalmente"] = meta["capturado_em_utc"]
    meta["capturado_em_utc"] = agora.isoformat()
    novo = destino / jpg.name
    novo.write_bytes(com_marca_de_replay(jpg.read_bytes(), marca))
    novo.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False))
    return novo


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camera", required=True)
    ap.add_argument("--de")
    ap.add_argument("--ate")
    ap.add_argument("--intervalo", type=float, default=2.0)
    ap.add_argument("--manifest", type=Path, default=RAIZ / "ml/data/manifests/manifest_coleta_fixa.csv")
    ap.add_argument("--raiz-frames", type=Path, default=RAIZ / "ml/data/raw/coleta_fixa")
    ap.add_argument("--config", type=Path, default=RAIZ / "ml/configs/coleta_fixa.yaml")
    ap.add_argument("--tokens", type=Path, default=RAIZ / "ml/configs/coleta_fixa_tokens.json")
    ap.add_argument("--api", help="URL do /ingest (default: backend_url do YAML)")
    args = ap.parse_args()

    url = args.api or yaml.safe_load(args.config.read_text())["backend_url"]
    token = token_da_fonte(args.camera, args.tokens)
    if not token:
        sys.exit(f"sem token para {args.camera}: defina CITYRAIN_TOKEN_{args.camera.upper()} ou {args.tokens}")
    frames = selecionar_frames(args.manifest, args.camera, _quando(args.de) if args.de else None,
                               _quando(args.ate) if args.ate else None, args.raiz_frames)
    print(f"[replay] {len(frames)} frames de {args.camera} -> {url}", flush=True)
    tmp = Path(tempfile.mkdtemp(prefix="replay_"))
    try:
        for jpg in frames:
            agora = datetime.now(timezone.utc)
            novo = preparar_frame_replay(jpg, tmp, agora, agora.isoformat())
            original = json.loads(novo.with_suffix(".json").read_text())["capturado_originalmente"]
            demo = {"origem": "replay_evento", "camera": args.camera, "capturado_originalmente": original}
            status = enviar_frame(novo, url, token, demo=demo)
            print(f"  {jpg.name} (gravado {original}) -> {status or 'sem rede'}", flush=True)
            time.sleep(args.intervalo)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
