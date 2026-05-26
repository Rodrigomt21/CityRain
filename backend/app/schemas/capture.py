from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.schemas.media import MediaFileResponse
from app.schemas.ingestion_log import IngestionLogResponse


class CaptureIngest(BaseModel):
    """
    Campos do JSON enviado no campo 'metadata' do multipart/form-data.

    O modelo CNN roda na NVIDIA Jetson antes do envio — weather_label e confidence
    são calculados na borda e obrigatoriamente incluídos no payload.
    """

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    captured_at: datetime = Field(..., description="ISO 8601 UTC. Ex: 2026-05-01T14:30:00Z")
    source_type: str = Field(default="jetson")
    weather_label: str = Field(..., description="Classificação da CNN. Ex: 'rain', 'no_rain'")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confiança da CNN (0.0–1.0)")
    metadata: Optional[dict[str, Any]] = None


class CaptureResponse(BaseModel):
    """Resposta padrão de captura — usada em listagens e após ingestão."""

    id: int
    captured_at: datetime
    received_at: datetime
    latitude: float
    longitude: float
    weather_label: str
    confidence: float
    source_type: str
    device_id: Optional[int] = None
    # validation_alias mapeia metadata_ do ORM para "metadata" no JSON
    metadata: Optional[dict[str, Any]] = Field(default=None, validation_alias="metadata_")

    model_config = {"from_attributes": True, "populate_by_name": True}


class CaptureWithDetails(CaptureResponse):
    """Resposta expandida com mídias e logs — usada em GET /captures/{id}."""

    media_files: list[MediaFileResponse] = []
    ingestion_logs: list[IngestionLogResponse] = []
