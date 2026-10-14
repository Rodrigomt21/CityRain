#!/usr/bin/env python3
"""Seleciona candidatos a SECO (visual) da coleta de maio/2026 para o gate da Jetson.

Regra de rótulo: no gate o rótulo é VISUAL (vidro sem gota + pista seca), porque o gate é um
detector de gota; rótulo de intensidade continua só de pluviômetro. Fonte: pré-rotulagem do
modelo (``classificador/pre_rotulagem.json``), só 20260520 'sem_chuva' com confiança >= 0,8
(20260523 fica de fora: pista molhada/gotas). Remove 'motivo' que cita molhado/gota/reflexo
(sem negação), tira quase-duplicatas por stride e separa dia/noite pelo brilho médio.
Saída: ml/data/review/gate_maio_seco/{candidatos.json, painel_*.jpg}
"""
import json, random, re, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parents[3]
BR = RAIZ.parent / "classificador" / "imagens_brutas"
PRE = RAIZ.parent / "classificador" / "pre_rotulagem.json"
OUT = RAIZ / "ml/data/review/gate_maio_seco"
NEG = re.compile(r"(sem|n[aã]o (h[aá]|ha|vis[ií]vel|visiveis|observ\w+|se v[eê]\w*|apresenta)|nenhum\w*|aus[eê]ncia de)( \w+){0,3}? (gotas?|pingos?|respingos?|chuva|umidade|reflexos?)")
RUIM = re.compile(r"molhad|[uú]mid|pingo|gotas?|reflex|embaça|respingo|chuvisc|garoa")
STRIDE = 2  # quase-duplicatas: frames consecutivos (ordem de nome)


def main() -> None:
    p = json.load(open(PRE))
    ks = sorted(k for k, v in p.items() if "20260520" in k and v["label"] == "sem_chuva" and v["confianca"] >= 0.8)
    bons = [k for k in ks if not RUIM.search(NEG.sub("", p[k]["motivo"].lower()))]
    print(f"sem_chuva>=0,8: {len(ks)} | motivo limpo: {len(bons)}")
    bons = [k for k in bons if (BR / k).exists() and (BR / k).stat().st_size][::STRIDE]
    print("após stride:", len(bons))
    lum = {k: float(np.asarray(Image.open(BR / k).convert("L").resize((64, 36))).mean()) for k in bons}
    res = {k: {"brilho": round(b, 1), "periodo": "dia" if b >= 70 else "noite"} for k, b in lum.items()}
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(res, open(OUT / "candidatos.json", "w"), indent=1)
    for per in ("dia", "noite"):
        n = sum(v["periodo"] == per for v in res.values()); print(per, n)
    rng = random.Random(7)
    for per in ("dia", "noite"):
        ks2 = [k for k, v in res.items() if v["periodo"] == per]
        rng.shuffle(ks2)
        for pi in range(3):
            im = Image.new("RGB", (6 * 240, 4 * 150))
            for i, k in enumerate(ks2[pi * 24:(pi + 1) * 24]):
                im.paste(Image.open(BR / k).convert("RGB").resize((240, 150)), ((i % 6) * 240, (i // 6) * 150))
                ImageDraw.Draw(im).text(((i % 6) * 240 + 3, (i // 6) * 150 + 3), k[15:21], fill=(255, 255, 0))
            im.save(OUT / f"painel_{per}_{pi + 1}.jpg", quality=85)


if __name__ == "__main__":
    main()
