from typing import Dict

from pydantic import BaseModel


class GeoStatsResponse(BaseModel):
    """Agrupamento de capturas por célula H3 para o mapa de calor do dashboard."""

    cell: str
    count: int
    labels: Dict[str, int]
