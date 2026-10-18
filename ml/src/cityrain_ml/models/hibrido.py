"""Híbrido exportável: CNN + atributos físicos da imagem calculados em tensor, num único ONNX.

Os atributos do ``baseline_fisico.py`` usam OpenCV; aqui os que mais acompanham a chuva entre dias de
para-brisa (CV por evento, 17/10/2026: brilho −0,67 e dark channel −0,49 de Spearman por evento) são
recalculados com operações de tensor sobre a MESMA entrada da CNN (normalizada ImageNet), para o backend
continuar chamando um ONNX só, sem OpenCV. Uma regressão logística (``combinador``) junta log-probs da CNN
e atributos padronizados e devolve 3 logits.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

MEDIA = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
DESVIO = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)
NOMES = ("brilho", "saturacao", "dark_channel", "contraste_rms", "var_laplaciano")


class AtributosFisicos(nn.Module):
    """N x 3 x H x W normalizado (ImageNet) -> N x 5 atributos em [0, 1]-ish."""

    def __init__(self) -> None:
        super().__init__()
        self.register_buffer("media", MEDIA.clone())
        self.register_buffer("desvio", DESVIO.clone())
        lap = torch.tensor([[0.0, 1.0, 0.0], [1.0, -4.0, 1.0], [0.0, 1.0, 0.0]]).view(1, 1, 3, 3)
        self.register_buffer("lap", lap)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        rgb = (x * self.desvio + self.media).clamp(0, 1)
        mx = rgb.amax(1, keepdim=True)
        mn = rgb.amin(1, keepdim=True)
        brilho = mx.mean((1, 2, 3))                                   # V do HSV
        saturacao = ((mx - mn) / (mx + 1e-6)).mean((1, 2, 3))        # S do HSV
        dark = -F.max_pool2d(-mn, 15, stride=1, padding=7)           # erosão 15x15 do mínimo dos canais
        cinza = (0.299 * rgb[:, 0:1] + 0.587 * rgb[:, 1:2] + 0.114 * rgb[:, 2:3])
        contraste = cinza.flatten(1).std(1)
        lap = F.conv2d(cinza, self.lap, padding=1)
        return torch.stack([brilho, saturacao, dark.mean((1, 2, 3)), contraste, lap.flatten(1).var(1) * 100], 1)


class Hibrido(nn.Module):
    """logits = W · [log p_CNN, (atributos − média) / desvio] + b."""

    def __init__(self, cnn: nn.Module, media: torch.Tensor, desvio: torch.Tensor, coef: torch.Tensor, intercepto: torch.Tensor) -> None:
        super().__init__()
        self.cnn = cnn
        self.fis = AtributosFisicos()
        self.register_buffer("m", media.float())
        self.register_buffer("s", desvio.float())
        self.combinador = nn.Linear(coef.shape[1], coef.shape[0])
        with torch.no_grad():
            self.combinador.weight.copy_(coef.float())
            self.combinador.bias.copy_(intercepto.float())

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        lp = torch.log_softmax(self.cnn(x), 1)
        z = torch.cat([lp, self.fis(x)], 1)
        return self.combinador((z - self.m) / self.s)
