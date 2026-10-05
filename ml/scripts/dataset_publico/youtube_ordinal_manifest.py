"""Gera manifest_youtube_ordinal.csv (D5): dashcam externa diurna, rotulo fraco >=moderada.

Selecao visual (grades em data/review/youtube_ordinal/). Frames quase pretos
(luminancia media < 15, fade in/out) sao descartados; depois stride uniforme,
ate 200 frames por video. frames11: inicio = frames 1-26 (legenda "just starting
to sprinkle" -> "it really started raining"); frames 27-28 (legenda "Sheets of
rain and WIND!", transicao) excluidos; pico = 29-52 (legendas somem, temporal).
"""
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

ML = Path(__file__).resolve().parents[2]
YT = ML / "data/processed/youtube"
MAX_FRAMES = 200
# frames14 EXCLUIDO apos inspecao: chuva fraca/ausente na maior parte, cartao de titulo "ANOLIPA".
# video -> (observacao, confianca_rotulo)
VIDEOS = {
    7: ("pip_motorista_canto_sup_dir", "media"),
    8: ("", "alta"),
    11: ("legenda_inferior_frames_1-28;10x_frames_5-15", "alta"),
    13: ("tuneis_ocasionais;hud_velocimetro_pequeno", "media"),
}


def trecho(v: int, n: int) -> str | None:
    if v != 11:
        return "unico"
    if n <= 26:
        return "inicio"
    if n >= 29:
        return "pico"
    return None


def main() -> None:
    meta = pd.read_csv(YT / "manifest.csv").set_index("idx")
    rows = []
    for v, (obs, conf) in VIDEOS.items():
        cand = []
        for p in sorted((YT / f"frames{v}").glob("frame_*.jpg")):
            n = int(p.stem.split("_")[1])
            t = trecho(v, n)
            if t is None:
                continue
            lum = np.asarray(Image.open(p).convert("L").resize((64, 36))).mean()
            if lum < 15:
                continue
            cand.append((n, p, t))
        if len(cand) > MAX_FRAMES:
            cand = [cand[i] for i in np.linspace(0, len(cand) - 1, MAX_FRAMES).round().astype(int)]
        for n, p, t in cand:
            rows.append({
                "caminho": str(p.relative_to(ML)), "video": f"youtube_frames{v}",
                "video_id": meta.loc[v, "source_id"], "frame": n, "t_video_s": n - 1,
                "trecho": t, "rotulo_fraco": ">=moderada", "particao": "test_ordinal_youtube",
                "origem": "youtube", "evento_id": f"youtube__frames{v}",
                "confianca_rotulo": conf, "observacao": obs,
            })
    out = ML / "data/manifests/manifest_youtube_ordinal.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(pd.DataFrame(rows).groupby(["video", "trecho"]).size())


if __name__ == "__main__":
    main()
