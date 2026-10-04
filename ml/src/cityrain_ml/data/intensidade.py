"""Dataset do modelo de intensidade a partir de ``ml/data/splits/intensidade_v1.csv`` (D3).

Uma linha do CSV = um frame, com ``caminho`` relativo à raiz do repo, ``classe``
(garoa | moderada | forte | seco | vazio), ``particao`` e ``origem``. Partições
ordinais (23/09, YouTube) não têm classe: o rótulo devolvido é ``-1`` e elas só
servem para a taxa de ordenação.

Pré-processamento congelado (vai junto com o checkpoint): PIL RGB → resize
bilinear para ``altura×largura`` → /255 → normalização ImageNet. Mesmo cuidado do
``detector.py`` da Jetson: nada de OpenCV/BGR aqui.
"""

from __future__ import annotations

import csv
import io
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance

MEDIA = np.array([0.485, 0.456, 0.406], dtype=np.float32)
DESVIO = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def ler_split(csv_path: Path, particoes: set[str] | None = None) -> list[dict[str, str]]:
    """Linhas do CSV de splits, opcionalmente filtradas por partição."""
    with open(csv_path, newline="") as f:
        linhas = list(csv.DictReader(f))
    if particoes is not None:
        linhas = [r for r in linhas if r["particao"] in particoes]
    return linhas


def preparar(img: Image.Image, altura: int, largura: int) -> np.ndarray:
    """PIL → array 3×H×W float32 normalizado (o mesmo no treino e na inferência)."""
    img = img.convert("RGB").resize((largura, altura), Image.BILINEAR)
    x = np.asarray(img, dtype=np.float32) / 255.0
    x = (x - MEDIA) / DESVIO
    return np.ascontiguousarray(x.transpose(2, 0, 1))


def aumentar(img: Image.Image, rng: random.Random, cfg: dict) -> Image.Image:
    """Aumentação leve, aplicada a TODAS as classes por igual.

    A recompressão JPEG existe para tirar um atalho específico deste dataset:
    o sintético foi salvo como JPEG por cima de um JPEG (dupla compressão) e o
    real não. Recomprimindo tudo com qualidade aleatória, a assinatura da
    compressão deixa de separar as classes.
    """
    if cfg.get("flip_horizontal", True) and rng.random() < 0.5:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    escala = cfg.get("recorte_escala_min", 1.0)
    if escala < 1.0:
        w, h = img.size
        s = rng.uniform(escala, 1.0)
        cw, ch = int(w * s), int(h * s)
        x0, y0 = rng.randint(0, w - cw), rng.randint(0, h - ch)
        img = img.crop((x0, y0, x0 + cw, y0 + ch))
    jit = cfg.get("brilho_contraste", 0.0)
    if jit > 0:
        img = ImageEnhance.Brightness(img).enhance(rng.uniform(1 - jit, 1 + jit))
        img = ImageEnhance.Contrast(img).enhance(rng.uniform(1 - jit, 1 + jit))
    qmin = cfg.get("jpeg_qualidade_min")
    if qmin:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=rng.randint(int(qmin), 95))
        buf.seek(0)
        img = Image.open(buf)
        img.load()
    return img


class DatasetIntensidade:
    """Dataset map-style compatível com ``torch.utils.data.DataLoader``.

    Não herda de ``torch.utils.data.Dataset`` para o módulo importar sem
    PyTorch (os testes rodam sem ele); o DataLoader só exige ``__len__`` e
    ``__getitem__``.
    """

    def __init__(
        self,
        linhas: list[dict[str, str]],
        raiz: Path,
        classes: tuple[str, ...],
        altura: int,
        largura: int,
        aumentacao: dict | None = None,
        seed: int = 0,
    ) -> None:
        self.linhas = linhas
        self.raiz = Path(raiz)
        self.indice = {c: i for i, c in enumerate(classes)}
        self.altura, self.largura = altura, largura
        self.aumentacao = aumentacao
        self.seed = seed
        self.epoca = 0

    def __len__(self) -> int:
        return len(self.linhas)

    def rotulo(self, i: int) -> int:
        return self.indice.get(self.linhas[i]["classe"], -1)

    def __getitem__(self, i: int) -> tuple[np.ndarray, int]:
        r = self.linhas[i]
        img = Image.open(self.raiz / r["caminho"])
        if self.aumentacao:
            rng = random.Random(hash((self.seed, self.epoca, i)))
            img = aumentar(img, rng, self.aumentacao)
        return preparar(img, self.altura, self.largura), self.rotulo(i)
