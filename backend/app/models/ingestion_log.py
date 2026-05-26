from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.capture import Capture


class IngestionLog(Base):
    """Registro de auditoria de cada tentativa de ingestão."""

    __tablename__ = "ingestion_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    capture_id: Mapped[int] = mapped_column(ForeignKey("captures.id"), index=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    protocol: Mapped[str] = mapped_column(String(20))   # ex: "http_multipart"
    status: Mapped[str] = mapped_column(String(10))     # "success" | "error"
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    capture: Mapped["Capture"] = relationship(back_populates="ingestion_logs")
