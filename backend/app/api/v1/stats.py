from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.capture_service import CaptureService
from app.services.geo_service import GeoService

router = APIRouter()


@router.get("/geo")
async def get_captures_geo(
    resolution: int = Query(
        default=8,
        ge=0,
        le=GeoService.H3_BASE_RESOLUTION,
        description=(
            "Resolução H3 (0=continentes, 10=~70m). 8 ≈ blocos de cidade. "
            f"Máximo {GeoService.H3_BASE_RESOLUTION}: resolução em que as células são gravadas."
        ),
    ),
    device_id: Optional[int] = Query(
        default=None,
        description="Filtrar mapa de calor por veículo específico.",
    ),
    from_date: Optional[datetime] = Query(default=None, description="Data inicial ISO 8601"),
    to_date: Optional[datetime] = Query(default=None, description="Data final ISO 8601"),
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna capturas agrupadas por célula H3 com contagem por weather_label.
    Alimenta o mapa de calor de chuva do dashboard.

    A agregação roda no banco; capturas antigas sem h3_cell não aparecem.

    Exemplo de resposta:
    [{"cell": "88a8dc25cdfffff", "count": 14, "labels": {"forte": 10, "seco": 4}}]
    """
    service = CaptureService(db)
    return await service.get_h3_heatmap(resolution, device_id, from_date, to_date)
