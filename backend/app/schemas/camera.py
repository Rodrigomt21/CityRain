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
