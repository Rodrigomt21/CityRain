from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class DeviceCreate(BaseModel):
    """Payload para registrar um novo dispositivo embarcado."""

    name: str = Field(..., min_length=1, max_length=100, description='Ex: "carro-01"')
    vehicle_plate: Optional[str] = Field(default=None, max_length=20)
    hw_model: Optional[str] = Field(default=None, max_length=50, description='Ex: "jetson_xavier"')
    metadata_: Optional[dict[str, Any]] = None


class DeviceResponse(BaseModel):
    """Resposta padrão de device — api_key_hash nunca é exposto."""

    id: int
    name: str
    vehicle_plate: Optional[str]
    hw_model: Optional[str]
    is_active: bool
    registered_at: datetime
    last_seen_at: Optional[datetime]

    model_config = {"from_attributes": True}


class DeviceCreatedResponse(DeviceResponse):
    """
    Retornado apenas no POST /devices — inclui a chave em texto puro.

    Esta é a ÚNICA vez que a chave aparece. Armazene-a imediatamente no Jetson;
    ela não pode ser recuperada depois.
    """

    api_key: str
