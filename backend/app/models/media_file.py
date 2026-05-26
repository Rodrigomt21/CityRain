from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.capture import Capture


class MediaFile(Base):
    """Arquivo de mídia (imagem) associado a uma captura."""

    __tablename__ = "media_files"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    capture_id: Mapped[int] = mapped_column(ForeignKey("captures.id"), index=True)
    file_path: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(100))
    file_name: Mapped[str] = mapped_column(String(255))
    # SHA-256 garante que a mesma imagem não seja salva duas vezes no disco
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    capture: Mapped["Capture"] = relationship(back_populates="media_files")
