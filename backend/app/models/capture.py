from datetime import datetime
from typing import TYPE_CHECKING, List, Optional  # Optional mantido para metadata_

from sqlalchemy import DateTime, Float, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.device import Device
    from app.models.media_file import MediaFile
    from app.models.ingestion_log import IngestionLog


class Capture(Base):
    """Representa uma captura de imagem feita pela câmera embarcada na Jetson."""

    __tablename__ = "captures"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    latitude: Mapped[float] = mapped_column(Float, index=True)
    longitude: Mapped[float] = mapped_column(Float, index=True)
    # Classificados pela CNN na Jetson antes do envio — sempre preenchidos
    weather_label: Mapped[str] = mapped_column(String(50))
    confidence: Mapped[float] = mapped_column(Float)
    # metadata_ evita conflito com Base.metadata do SQLAlchemy; coluna no banco é "metadata"
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    source_type: Mapped[str] = mapped_column(String(20))
    # nullable para retrocompatibilidade — capturas antigas não têm device vinculado
    device_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("devices.id"), nullable=True, index=True
    )

    device: Mapped[Optional["Device"]] = relationship(back_populates="captures")
    media_files: Mapped[List["MediaFile"]] = relationship(
        back_populates="capture", cascade="all, delete-orphan"
    )
    ingestion_logs: Mapped[List["IngestionLog"]] = relationship(
        back_populates="capture", cascade="all, delete-orphan"
    )
