from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.capture import CaptureResponse, CaptureWithDetails
from app.services.camera_service import CameraService
from app.services.capture_service import CaptureService

router = APIRouter()


@router.get("/", response_model=list[CaptureResponse])
async def list_captures(
    skip: int = Query(default=0, ge=0, description="Quantas capturas pular (paginação)"),
    limit: int = Query(default=50, le=200, description="Máximo de capturas retornadas"),
    weather_label: Optional[Literal["seco", "garoa", "moderado", "forte"]] = Query(
        default=None, description="Filtrar por classe de chuva"
    ),
    from_date: Optional[datetime] = Query(default=None, description="Data inicial ISO 8601"),
    to_date: Optional[datetime] = Query(default=None, description="Data final ISO 8601"),
    excluir_demo: bool = Query(
        default=False, description="Exclui capturas de demonstração (metadata.demo), ex.: no histórico."
    ),
    device_id: Optional[int] = Query(default=None, description="Filtrar por ID do dispositivo"),
    tipo: Optional[Literal["movel", "fixa"]] = Query(default=None, description="Só câmeras fixas ou só móveis"),
    db: AsyncSession = Depends(get_db),
):
    """Lista capturas com filtros opcionais, ordenadas da mais recente para a mais antiga."""
    service = CaptureService(db)
    return await service.list_captures(
        skip, limit, weather_label, from_date, to_date, device_id=device_id, excluir_demo=excluir_demo, tipo=tipo
    )


@router.get("/{capture_id}/imagem")
async def imagem_da_captura(capture_id: int, db: AsyncSession = Depends(get_db)):
    """Arquivo da imagem; 404 se não houver ou se o disco do servidor não o tiver mais."""
    mf = await CameraService(db).arquivo_da_captura(capture_id)
    if mf is None or not Path(mf.file_path).is_file():
        raise HTTPException(status_code=404, detail="Imagem indisponível.")
    return FileResponse(mf.file_path, media_type=mf.mime_type)


@router.get("/{capture_id}", response_model=CaptureWithDetails)
async def get_capture(
    capture_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Retorna uma captura específica com seus arquivos de mídia e logs de ingestão."""
    service = CaptureService(db)
    capture = await service.get_by_id(capture_id)
    if not capture:
        raise HTTPException(status_code=404, detail="Captura não encontrada.")
    return capture
