from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.capture_service import CaptureService

router = APIRouter()


@router.get("/geo")
async def get_captures_geo(
    resolution: int = Query(
        default=8,
        ge=0,
        le=15,
        description="Resolução H3 (0=continentes, 15=metros). 8 ≈ blocos de cidade.",
    ),
    device_id: Optional[int] = Query(
        default=None,
        description="Filtrar mapa de calor por veículo específico.",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna capturas agrupadas por célula H3 com contagem por weather_label.
    Alimenta o mapa de calor de chuva do dashboard.

    Exemplo de resposta:
    [{"cell": "88a8dc25cdfffff", "count": 14, "labels": {"rain": 10, "no_rain": 4}}]
    """
    service = CaptureService(db)
    return await service.get_h3_heatmap(resolution, device_id)
