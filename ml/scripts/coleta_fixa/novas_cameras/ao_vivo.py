#!/usr/bin/env python3
"""AO VIVO — coletor das suas câmeras: 1 foto por câmera a cada 10 min, enquanto o PC estiver ligado.

É o mesmo ml/scripts/coleta_fixa/coletor.py da equipe, com uma correção para Windows (o arquivo temporário
do original fica bloqueado e o ffmpeg falha com "Permission denied"). No Mac/Linux funciona igual.
As fotos vão para o "destino" da sua config (ml/data/raw/novas_<nome>/frames). Ctrl+C encerra.

Uso (da raiz CityRain/, venv ativo):
    python ml/scripts/coleta_fixa/novas_cameras/ao_vivo.py --nome paulo --uma-rodada   # teste
    python ml/scripts/coleta_fixa/novas_cameras/ao_vivo.py --nome paulo                # contínuo
No Mac, ponha "caffeinate -i " na frente para o computador não dormir.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import COLETA, carregar_config, config_path  # noqa: E402

sys.path.insert(0, str(COLETA))
import coletor  # noqa: E402


def _jpeg_youtube(fonte) -> bytes:
    """Igual ao coletor.py, mas com pasta temporária (funciona no Windows)."""
    import time
    agora = time.time()
    if not fonte.hls or agora - fonte.hls_em > coletor.RENOVAR_HLS_S:
        # --match-filter is_live: live encerrada vira gravação, e o 1º quadro da gravação sairia com a hora de agora
        r = subprocess.run(["yt-dlp", "-g", "--match-filter", "is_live", "-f", "b[height<=720]/bv*[height<=720]/b/bv*",
                            fonte.url], capture_output=True, text=True, timeout=coletor.TIMEOUT_S)
        if r.returncode != 0 or not r.stdout.strip():
            raise RuntimeError(f"yt-dlp: sem live no ar agora {r.stderr.strip()[-200:]}")
        fonte.hls, fonte.hls_em = r.stdout.strip().splitlines()[0], agora
    # HLS em cache de live que acabou ganha #EXT-X-ENDLIST: o ffmpeg leria do começo da gravação
    try:
        lista = urllib.request.urlopen(fonte.hls, timeout=20).read(400_000).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        lista = ""
    if "#EXT-X-ENDLIST" in lista:
        fonte.hls = ""
        raise RuntimeError("live encerrada (playlist com ENDLIST): foto descartada")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir) / "frame.jpg"
        r = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", fonte.hls, "-frames:v", "1", "-q:v", "2", str(tmp)],
                           capture_output=True, text=True, timeout=coletor.TIMEOUT_S)
        if r.returncode != 0:
            fonte.hls = ""
            raise RuntimeError(f"ffmpeg: {r.stderr.strip()[-200:]}")
        return tmp.read_bytes()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nome", required=True)
    ap.add_argument("--uma-rodada", action="store_true")
    ap.add_argument("--intervalo-s", type=float, default=600)
    args = ap.parse_args()
    cfg = carregar_config(args.nome)
    if not str(cfg.get("destino", "")).startswith(f"ml/data/raw/novas_{args.nome}"):
        raise SystemExit(f"Na sua config, use destino: ml/data/raw/novas_{args.nome}/frames (para não misturar com a coleta do Guilherme).")
    coletor.CAPTURAS["youtube"] = _jpeg_youtube
    sys.argv = ["coletor.py", str(config_path(args.nome)), "--intervalo-s", str(args.intervalo_s)]
    if args.uma_rodada:
        sys.argv.append("--uma-rodada")
    coletor.main()


if __name__ == "__main__":
    main()
