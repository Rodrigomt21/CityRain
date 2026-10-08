from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.camera import CameraResumo, PontoSerie
from app.services.camera_service import CameraService

router = APIRouter()


@router.get("/", response_model=list[CameraResumo])
async def listar_cameras(
    excluir_demo: bool = Query(default=False, description="Ignora capturas de demonstração na última captura"),
    db: AsyncSession = Depends(get_db),
):
    """Câmeras fixas com a última captura classificada (público, sem credencial)."""
    return await CameraService(db).listar(excluir_demo)


@router.get("/{device_id}/serie", response_model=list[PontoSerie])
async def serie_camera(
    device_id: int,
    horas: int = Query(default=6, ge=1, le=48),
    excluir_demo: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    """Classes previstas nas últimas `horas`, em ordem de tempo."""
    serie = await CameraService(db).serie(device_id, horas, excluir_demo)
    if serie is None:
        raise HTTPException(status_code=404, detail="Câmera fixa não encontrada.")
    return serie
