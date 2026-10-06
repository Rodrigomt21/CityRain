#!/usr/bin/env python3
"""Grad-CAM do modelo de intensidade: onde o modelo olha, por domínio.

Gera uma figura com, para cada domínio (garoa da nossa câmera, 23/09, YouTube forte,
irCNN dia e noite), a imagem e o mapa de ativação da classe prevista (Grad-CAM,
Selvaraju et al. 2017) sobre o último bloco convolucional. Com ``--comparar`` põe
lado a lado dois checkpoints na mesma imagem (ex.: v1 sem irCNN x v3), que é a
forma mais direta de mostrar um atalho de domínio.

Uso:
    ml/.venv/bin/python ml/scripts/avaliacao/gradcam.py --ckpt ml/runs/<final>/melhor.pt \
        [--comparar ml/runs/<v1>/melhor.pt] --saida ml/resultados/figuras/gradcam.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
from PIL import Image, ImageDraw, ImageFont

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "ml" / "src"))

from cityrain_ml.data.intensidade import preparar  # noqa: E402
from cityrain_ml.evaluation.metricas import CLASSES  # noqa: E402
from cityrain_ml.models.fabrica import construir  # noqa: E402


def carregar(ckpt: Path) -> tuple[torch.nn.Module, int, int, str]:
    e = torch.load(ckpt, map_location="cpu", weights_only=False)
    cfg = e["config"]
    m = construir(cfg["modelo"]["arquitetura"], len(CLASSES), pretreinado=False)
    m.load_state_dict(e["estado"])
    return m.eval(), cfg["entrada"]["altura"], cfg["entrada"]["largura"], cfg["nome"]


def gradcam(m: torch.nn.Module, x: torch.Tensor) -> tuple[np.ndarray, int, float]:
    """Mapa Grad-CAM (0..1, tamanho da entrada) da classe prevista."""
    alvo = m.features[-1]  # último bloco conv (MobileNetV3 / EfficientNet)
    ativ, grad = {}, {}
    h1 = alvo.register_forward_hook(lambda _m, _i, o: ativ.__setitem__("a", o))
    h2 = alvo.register_full_backward_hook(lambda _m, _gi, go: grad.__setitem__("g", go[0]))
    try:
        z = m(x)
        k = int(z.argmax(1))
        conf = float(torch.softmax(z, 1)[0, k])
        m.zero_grad()
        z[0, k].backward()
    finally:
        h1.remove()
        h2.remove()
    pesos = grad["g"].mean(dim=(2, 3), keepdim=True)
    cam = torch.relu((pesos * ativ["a"]).sum(1))[0].detach().numpy()
    cam = cv2.resize(cam, (x.shape[3], x.shape[2]))
    return (cam - cam.min()) / (cam.max() - cam.min() + 1e-8), k, conf


def sobrepor(img: Image.Image, cam: np.ndarray) -> Image.Image:
    base = np.asarray(img.convert("RGB").resize((cam.shape[1], cam.shape[0])), dtype=np.float32)
    calor = cv2.applyColorMap(np.uint8(255 * cam), cv2.COLORMAP_JET)[:, :, ::-1].astype(np.float32)
    return Image.fromarray(np.uint8(0.55 * base + 0.45 * calor))


def exemplos(df: pd.DataFrame) -> list[tuple[str, str]]:
    ir = df[df.particao == "test_ircnn"]
    yt = df[df.particao == "test_ordinal_youtube"]
    escolha = [
        ("Garoa 13/09 (nossa câmera)", df[df.particao == "test_real"].caminho.iloc[[30, 120]]),
        ("Chuva 23/09 (nossa câmera)", df[df.particao == "test_ordinal_2309"].caminho.iloc[[40, 200]]),
        ("YouTube forte (para-brisa)", pd.concat([yt[yt.trecho == "pico"].caminho.iloc[[5]], yt[yt.caminho.str.contains("frames8/")].caminho.iloc[[60]]])),
        ("irCNN forte, dia", ir[(ir.classe == "forte") & (ir.periodo == "dia")].caminho.iloc[[100, 2000]]),
        ("irCNN forte, noite", ir[(ir.classe == "forte") & (ir.periodo == "noite")].caminho.iloc[[100, 2000]]),
    ]
    return [(nome, c) for nome, s in escolha for c in s]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ckpt", type=Path, required=True)
    ap.add_argument("--comparar", type=Path)
    ap.add_argument("--splits", type=Path, default=RAIZ / "ml/data/splits/intensidade_v1.csv")
    ap.add_argument("--saida", type=Path, required=True)
    args = ap.parse_args()

    modelos = [carregar(args.ckpt)] + ([carregar(args.comparar)] if args.comparar else [])
    linhas = exemplos(pd.read_csv(args.splits))
    W, H = 384, 288
    colunas = 1 + len(modelos)
    fig = Image.new("RGB", (W * colunas, (H + 28) * len(linhas)), (18, 22, 30))
    d = ImageDraw.Draw(fig)
    try:
        fonte = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 15)
    except OSError:
        fonte = ImageFont.load_default()
    for i, (dominio, caminho) in enumerate(linhas):
        img = Image.open(RAIZ / caminho).convert("RGB")
        y = i * (H + 28)
        fig.paste(img.resize((W, H)), (0, y + 28))
        d.text((6, y + 6), dominio, fill=(230, 230, 230), font=fonte)
        for j, (m, h, w, nome) in enumerate(modelos):
            x = torch.from_numpy(preparar(img, h, w))[None].requires_grad_(True)
            cam, k, conf = gradcam(m, x)
            fig.paste(sobrepor(img, cam).resize((W, H)), ((j + 1) * W, y + 28))
            d.text(((j + 1) * W + 6, y + 6), f"{nome.replace('intensidade_', '')}: {CLASSES[k]} ({conf:.0%})",
                   fill=(255, 220, 120), font=fonte)
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    fig.save(args.saida, quality=90)
    print(f"[gradcam] {args.saida} ({len(linhas)} exemplos x {len(modelos)} modelo(s))")


if __name__ == "__main__":
    main()
