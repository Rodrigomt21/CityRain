"""Fábrica de arquiteturas candidatas (nenhuma é a escolha final — ver CLAUDE.md).

Todas vêm do torchvision com pesos ImageNet e têm a última camada trocada por
uma de ``n_classes`` saídas. Com ``canais_entrada=6`` a entrada é imagem + referência seca
(modelo de câmera fixa, variante F3). Para comparar outra arquitetura basta acrescentar
uma entrada em ``_CONSTRUTORES`` e trocar ``modelo.arquitetura`` no YAML.
"""

from __future__ import annotations

from collections.abc import Callable

import torch
import torch.nn as nn
from torchvision import models as tvm


def _mobilenet_v3_large(pre: bool) -> tuple[nn.Module, Callable[[nn.Module, int], None]]:
    m = tvm.mobilenet_v3_large(weights="IMAGENET1K_V2" if pre else None)

    def cabeca(m: nn.Module, n: int) -> None:
        m.classifier[3] = nn.Linear(m.classifier[3].in_features, n)

    return m, cabeca


def _mobilenet_v3_small(pre: bool) -> tuple[nn.Module, Callable[[nn.Module, int], None]]:
    m = tvm.mobilenet_v3_small(weights="IMAGENET1K_V1" if pre else None)

    def cabeca(m: nn.Module, n: int) -> None:
        m.classifier[3] = nn.Linear(m.classifier[3].in_features, n)

    return m, cabeca


def _efficientnet_b0(pre: bool) -> tuple[nn.Module, Callable[[nn.Module, int], None]]:
    m = tvm.efficientnet_b0(weights="IMAGENET1K_V1" if pre else None)

    def cabeca(m: nn.Module, n: int) -> None:
        m.classifier[1] = nn.Linear(m.classifier[1].in_features, n)

    return m, cabeca


def _resnet18(pre: bool) -> tuple[nn.Module, Callable[[nn.Module, int], None]]:
    m = tvm.resnet18(weights="IMAGENET1K_V1" if pre else None)

    def cabeca(m: nn.Module, n: int) -> None:
        m.fc = nn.Linear(m.fc.in_features, n)

    return m, cabeca


def _trocar_entrada(m: nn.Module, canais: int) -> None:
    """Primeira conv com ``canais`` entradas: pesos originais nos 3 primeiros, zero no resto."""
    if hasattr(m, "conv1"):
        velha, colocar = m.conv1, lambda nova: setattr(m, "conv1", nova)
    else:
        velha = m.features[0][0]

        def colocar(nova):
            m.features[0][0] = nova
    nova = nn.Conv2d(canais, velha.out_channels, velha.kernel_size, velha.stride, velha.padding,
                     dilation=velha.dilation, groups=velha.groups, bias=velha.bias is not None)
    with torch.no_grad():
        nova.weight.zero_()
        nova.weight[:, :3] = velha.weight
        if velha.bias is not None:
            nova.bias.copy_(velha.bias)
    colocar(nova)


_CONSTRUTORES = {
    "mobilenet_v3_large": _mobilenet_v3_large,
    "mobilenet_v3_small": _mobilenet_v3_small,
    "efficientnet_b0": _efficientnet_b0,
    "resnet18": _resnet18,
}


def construir(arquitetura: str, n_classes: int, pretreinado: bool = True, canais_entrada: int = 3) -> nn.Module:
    if arquitetura not in _CONSTRUTORES:
        raise ValueError(f"arquitetura desconhecida: {arquitetura!r} (opções: {sorted(_CONSTRUTORES)})")
    if canais_entrada not in (3, 6):
        raise ValueError(f"canais_entrada deve ser 3 ou 6, não {canais_entrada}")
    m, cabeca = _CONSTRUTORES[arquitetura](pretreinado)
    cabeca(m, n_classes)
    if canais_entrada == 6:
        _trocar_entrada(m, 6)
    return m
