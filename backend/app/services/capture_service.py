from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.capture import Capture
from app.services.geo_service import GeoService


class CaptureService:
    """Queries de leitura para o dashboard (React e Streamlit)."""

    def __init__(self, db: AsyncSession) -> None:
        """Inicializa o serviço com a sessão de banco da requisição."""
        self.db = db

    async def list_captures(
        self,
        skip: int,
        limit: int,
        weather_label: Optional[str],
        from_date: Optional[datetime],
        to_date: Optional[datetime],
        device_id: Optional[int] = None,
    ) -> list[Capture]:
        """Lista capturas com filtros opcionais, ordenadas da mais recente para a mais antiga."""
        query = select(Capture).order_by(Capture.captured_at.desc())

        if weather_label:
            query = query.where(Capture.weather_label == weather_label)
        if from_date:
            query = query.where(Capture.captured_at >= from_date)
        if to_date:
            query = query.where(Capture.captured_at <= to_date)
        if device_id is not None:
            query = query.where(Capture.device_id == device_id)

        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_by_id(self, capture_id: int) -> Optional[Capture]:
        """
        Busca captura por ID com relacionamentos carregados antecipadamente.

        selectinload é obrigatório em async: SQLAlchemy não faz lazy loading
        em sessões assíncronas — acessar .media_files sem isso levanta um erro.
        """
        result = await self.db.execute(
            select(Capture)
            .where(Capture.id == capture_id)
            .options(
                selectinload(Capture.media_files),
                selectinload(Capture.ingestion_logs),
            )
        )
        return result.scalar_one_or_none()

    async def get_h3_heatmap(
        self, resolution: int, device_id: Optional[int] = None
    ) -> list[dict]:
        """Retorna capturas agrupadas por célula H3 para o mapa de calor do dashboard."""
        query = select(Capture.latitude, Capture.longitude, Capture.weather_label)
        if device_id is not None:
            query = query.where(Capture.device_id == device_id)
        result = await self.db.execute(query)
        rows = [dict(r._mapping) for r in result.all()]
        return GeoService.group_by_h3(rows, resolution)
