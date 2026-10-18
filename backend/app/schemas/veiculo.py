"""Visão pública dos veículos (dispositivos móveis) para o dashboard."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class UltimaCapturaVeiculo(BaseModel):
    """Última captura de um veículo. Sem imagem: frames do carro nunca saem do backend (LGPD)."""

    id: int
    captured_at: datetime
    latitude: float
    longitude: float
    weather_label: Optional[str] = None  # None = não medido, nunca renderizar como seco
    confidence: Optional[float] = None
    modelo: Optional[str] = None
    demo: bool = False  # metadata.demo: replay da defesa, não chuva real

    @classmethod
    def da_captura(cls, cap) -> "UltimaCapturaVeiculo":
        """Monta a partir do model Capture, derivando `demo` de metadata_."""
        return cls(
            id=cap.id, captured_at=cap.captured_at, latitude=cap.latitude, longitude=cap.longitude,
            weather_label=cap.weather_label, confidence=cap.confidence, modelo=cap.modelo,
            demo=bool((cap.metadata_ or {}).get("demo")),
        )


class VeiculoResumo(BaseModel):
    """Veículo ativo, sem placa e sem credencial, com a última captura."""

    id: int
    name: str
    hw_model: Optional[str] = None
    is_active: bool
    last_seen_at: Optional[datetime] = None
    ultima_captura: Optional[UltimaCapturaVeiculo] = None
