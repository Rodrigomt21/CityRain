from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.schemas.media import MediaFileResponse
from app.schemas.ingestion_log import IngestionLogResponse


class CaptureIngest(BaseModel):
    """
    Campos do JSON enviado no campo 'metadata' do multipart/form-data.

    weather_label e confidence não são enviados pela Jetson — o backend
    classifica a intensidade com seu próprio modelo. Enquanto não houver modelo
    carregado, a captura é persistida com intensidade nula ("não medida").
    """

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    captured_at: datetime = Field(..., description="ISO 8601 UTC. Ex: 2026-05-01T14:30:00Z")
    source_type: str = Field(default="jetson")
    metadata: Optional[dict[str, Any]] = None


class CaptureResponse(BaseModel):
    """Resposta padrão de captura — usada em listagens e após ingestão."""

    id: int
    captured_at: datetime
    received_at: datetime
    latitude: float
    longitude: float
    # None = intensidade não medida. Não renderizar como "seco" no dashboard.
    weather_label: Optional[str] = None
    confidence: Optional[float] = None
    modelo: Optional[str] = None
    modelo_versao: Optional[str] = None
    source_type: str
    device_id: Optional[int] = None
    # validation_alias mapeia metadata_ do ORM para "metadata" no JSON
    metadata: Optional[dict[str, Any]] = Field(default=None, validation_alias="metadata_")

    model_config = {"from_attributes": True, "populate_by_name": True}


class CaptureWithDetails(CaptureResponse):
    """Resposta expandida com mídias e logs — usada em GET /captures/{id}."""

    media_files: list[MediaFileResponse] = []
    ingestion_logs: list[IngestionLogResponse] = []
