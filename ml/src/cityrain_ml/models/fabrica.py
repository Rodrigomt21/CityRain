"""Fábrica de arquiteturas candidatas (nenhuma é a escolha final — ver CLAUDE.md).

Todas vêm do torchvision com pesos ImageNet e têm a última camada trocada por
uma de ``n_classes`` saídas. Para comparar outra arquitetura basta acrescentar
uma entrada em ``_CONSTRUTORES`` e trocar ``modelo.arquitetura`` no YAML.
"""

from __future__ import annotations

from collections.abc import Callable

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


_CONSTRUTORES = {
    "mobilenet_v3_large": _mobilenet_v3_large,
    "mobilenet_v3_small": _mobilenet_v3_small,
    "efficientnet_b0": _efficientnet_b0,
    "resnet18": _resnet18,
}


def construir(arquitetura: str, n_classes: int, pretreinado: bool = True) -> nn.Module:
    if arquitetura not in _CONSTRUTORES:
        raise ValueError(f"arquitetura desconhecida: {arquitetura!r} (opções: {sorted(_CONSTRUTORES)})")
    m, cabeca = _CONSTRUTORES[arquitetura](pretreinado)
    cabeca(m, n_classes)
    return m
