"""Visão pública das câmeras fixas para o dashboard."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class UltimaCaptura(BaseModel):
    id: int
    captured_at: datetime
    weather_label: Optional[str] = None  # None = não medido, nunca renderizar como seco
    confidence: Optional[float] = None
    modelo: Optional[str] = None
    # Captura de demonstração (replay da defesa, metadata.demo): o dashboard avisa que não é chuva real
    demo: bool = False

    @classmethod
    def da_captura(cls, cap) -> "UltimaCaptura":
        """Monta a partir do model Capture, derivando `demo` de metadata_."""
        return cls(
            id=cap.id, captured_at=cap.captured_at, weather_label=cap.weather_label,
            confidence=cap.confidence, modelo=cap.modelo, demo=bool((cap.metadata_ or {}).get("demo")),
        )


class CameraResumo(BaseModel):
    id: int
    name: str
    descricao: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    stream_url: Optional[str] = None
    is_active: bool
    last_seen_at: Optional[datetime] = None
    ultima_captura: Optional[UltimaCaptura] = None
    imagem_url: Optional[str] = None


class PontoSerie(BaseModel):
    captured_at: datetime
    weather_label: Optional[str] = None
    confidence: Optional[float] = None
