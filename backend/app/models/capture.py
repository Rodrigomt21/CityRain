from datetime import datetime
from typing import TYPE_CHECKING, List, Optional  # Optional mantido para metadata_

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.device import Device
    from app.models.media_file import MediaFile
    from app.models.ingestion_log import IngestionLog


# Classes de INTENSIDADE. Alterar aqui exige migration (CHECK constraint).
# Não confundir com detecção: o gate binário da Jetson responde "há chuva?",
# nunca "quanto". weather_label=None significa intensidade não medida, e é
# diferente de "seco", que é uma medida de ausência de chuva.
WEATHER_LABELS = ("seco", "garoa", "moderado", "forte")


class Capture(Base):
    """Representa uma captura de imagem feita pela câmera embarcada na Jetson."""

    __tablename__ = "captures"
    __table_args__ = (
        # NULL é permitido: significa "intensidade não medida". Ver migration 0003.
        CheckConstraint(
            "weather_label IS NULL OR weather_label IN ('seco', 'garoa', 'moderado', 'forte')",
            name="ck_captures_weather_label",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # index=True: o dashboard sempre ordena/filtra por captured_at
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    latitude: Mapped[float] = mapped_column(Float, index=True)
    longitude: Mapped[float] = mapped_column(Float, index=True)
    # Célula H3 na resolução base (GeoService.H3_BASE_RESOLUTION), calculada na
    # ingestão. Permite agregar o heatmap com GROUP BY no banco em vez de
    # carregar todas as capturas em memória. Nullable: capturas pré-H3.
    h3_cell: Mapped[Optional[str]] = mapped_column(String(15), index=True, nullable=True)
    # Intensidade classificada pelo modelo do backend sobre a imagem recebida.
    # Ambos nullable: ficam None enquanto nenhum modelo de intensidade estiver
    # carregado — "não medido", nunca "seco". O único caso em que o backend
    # grava "seco" por conta própria é a captura sem imagem, em que a Jetson já
    # afirmou ausência de chuva ao descartar o frame.
    weather_label: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Qual ONNX classificou (metadata `experimento` e `epoca` do arquivo). Nulo quando
    # não houve inferência (captura sem imagem ou sem modelo carregado).
    modelo: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    modelo_versao: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
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
