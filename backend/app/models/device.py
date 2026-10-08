from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.capture import Capture


# 'movel' = Jetson no carro; 'fixa' = câmera parada sem Jetson. Alterar exige migration (CHECK).
DEVICE_TIPOS = ("movel", "fixa")


class Device(Base):
    """Representa um dispositivo embarcado (Jetson) cadastrado no sistema."""

    __tablename__ = "devices"
    __table_args__ = (CheckConstraint("tipo IN ('movel', 'fixa')", name="ck_devices_tipo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    vehicle_plate: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # SHA-256 hex da chave real — nunca armazenar a chave em texto puro
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    hw_model: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    tipo: Mapped[str] = mapped_column(String(10), default="movel", server_default="movel", index=True)
    # Só para câmera fixa: posição permanente e origem pública da imagem.
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stream_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    descricao: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    captures: Mapped[List["Capture"]] = relationship(back_populates="device")
