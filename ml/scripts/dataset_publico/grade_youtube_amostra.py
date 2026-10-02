"""Grade de amostras (uniforme) de um video YouTube para inspecao visual."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ML = Path(__file__).resolve().parents[2]
n, k = int(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 20
out = Path(sys.argv[3]) if len(sys.argv) > 3 else ML / f"data/review/youtube_ordinal/amostra_frames{n}.jpg"
fs = sorted((ML / f"data/processed/youtube/frames{n}").glob("*.jpg"))
idx = np.linspace(0, len(fs) - 1, k).astype(int)
cols = 5
W, H = 384, 216
g = Image.new("RGB", (W * cols, H * ((k + cols - 1) // cols)))
for i, j in enumerate(idx):
    im = Image.open(fs[j]).convert("RGB").resize((W, H))
    ImageDraw.Draw(im).text((5, 5), fs[j].stem[-5:], fill=(255, 255, 0))
    g.paste(im, ((i % cols) * W, (i // cols) * H))
g.save(out, quality=82)
