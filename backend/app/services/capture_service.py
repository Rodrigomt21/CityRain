from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
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
        self,
        resolution: int,
        device_id: Optional[int] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> list[dict]:
        """
        Retorna capturas agrupadas por célula H3 para o mapa de calor do dashboard.

        A agregação pesada acontece no banco (GROUP BY h3_cell, weather_label):
        a aplicação recebe uma linha por célula/label, não uma por captura —
        a memória cresce com a área coberta, não com o volume de capturas.
        """
        query = (
            select(Capture.h3_cell, Capture.weather_label, func.count().label("count"))
            .where(Capture.h3_cell.is_not(None))
            .group_by(Capture.h3_cell, Capture.weather_label)
        )
        if device_id is not None:
            query = query.where(Capture.device_id == device_id)
        if from_date:
            query = query.where(Capture.captured_at >= from_date)
        if to_date:
            query = query.where(Capture.captured_at <= to_date)

        result = await self.db.execute(query)
        return GeoService.aggregate_cells(list(result.all()), resolution)
