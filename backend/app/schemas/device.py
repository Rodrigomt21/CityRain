from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class DeviceCreate(BaseModel):
    """Payload para registrar um dispositivo: Jetson ('movel') ou câmera parada ('fixa')."""

    name: str = Field(..., min_length=1, max_length=100, description='Ex: "carro-01" ou "fixa-sp_centro_geolan"')
    vehicle_plate: Optional[str] = Field(default=None, max_length=20)
    hw_model: Optional[str] = Field(default=None, max_length=50, description='Ex: "jetson_xavier"')
    metadata_: Optional[dict[str, Any]] = None
    tipo: Literal["movel", "fixa"] = "movel"
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    stream_url: Optional[str] = Field(default=None, max_length=500)
    descricao: Optional[str] = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _fixa_tem_posicao(self) -> "DeviceCreate":
        if self.tipo == "fixa" and (self.latitude is None or self.longitude is None):
            raise ValueError("câmera fixa exige latitude e longitude no cadastro")
        return self


class DeviceResponse(BaseModel):
    """Resposta padrão de device — api_key_hash nunca é exposto."""

    id: int
    name: str
    vehicle_plate: Optional[str]
    hw_model: Optional[str]
    is_active: bool
    registered_at: datetime
    last_seen_at: Optional[datetime]
    tipo: str = "movel"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    stream_url: Optional[str] = None
    descricao: Optional[str] = None

    model_config = {"from_attributes": True}


class DevicePublico(BaseModel):
    """Visão pública de um device, para o dashboard sem credencial.

    Sem placa do veículo (dado pessoal) e sem nada de chave: o frontend é público, então
    qualquer coisa que ele precise ler não pode exigir a admin key.
    """

    id: int
    name: str
    hw_model: Optional[str]
    is_active: bool
    registered_at: datetime
    last_seen_at: Optional[datetime]
    tipo: str = "movel"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    stream_url: Optional[str] = None
    descricao: Optional[str] = None

    model_config = {"from_attributes": True}


class DeviceCreatedResponse(DeviceResponse):
    """
    Retornado apenas no POST /devices — inclui a chave em texto puro.

    Esta é a ÚNICA vez que a chave aparece. Armazene-a imediatamente no Jetson;
    ela não pode ser recuperada depois.
    """

    api_key: str
