"""Grade de revisao do irCNN: 4 frames por classe (indices uniformes, determinístico)."""
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw

ML = Path(__file__).resolve().parents[2]
d = pd.read_csv(ML / "data/manifests/manifest_ircnn.csv")
W, H = 480, 270
rows = []
for c in ["seco", "garoa", "moderada", "forte"]:
    s = d[d.classe == c].reset_index(drop=True)
    idx = np.linspace(0, len(s) - 1, 4).astype(int)
    row = Image.new("RGB", (W * 4, H))
    for k, j in enumerate(idx):
        r = s.iloc[j]
        im = Image.open(ML / r.caminho).resize((W, H))
        ImageDraw.Draw(im).text((6, 6), f"{c} {r.mm_h:.1f}mm/h {r.evento_id[-8:]} {r.periodo}", fill=(255, 0, 0))
        row.paste(im, (W * k, 0))
    rows.append(row)
g = Image.new("RGB", (W * 4, H * 4))
for i, r in enumerate(rows):
    g.paste(r, (0, H * i))
g.save(ML / "data/review/ircnn/grade_classes.jpg", quality=85)
