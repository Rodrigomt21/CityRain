import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verificar_api_key
from app.models.device import Device
from app.schemas.capture import CaptureResponse
from app.services.media_service import MediaService

router = APIRouter()


@router.post(
    "/ingest",
    response_model=CaptureResponse,
    status_code=201,
)
async def ingest_capture(
    image: UploadFile = File(..., description="Arquivo de imagem JPEG ou PNG"),
    metadata: str = Form(
        ...,
        description=(
            "JSON com campos obrigatórios: captured_at (ISO 8601), latitude, longitude, "
            "source_type, weather_label (resultado CNN) e confidence (0.0–1.0). "
            'Ex: {"captured_at":"2026-05-01T14:30:00Z","latitude":-23.92,"longitude":-46.89,'
            '"source_type":"jetson_xavier","weather_label":"rain","confidence":0.97}'
        ),
    ),
    db: AsyncSession = Depends(get_db),
    device: Device = Depends(verificar_api_key),
):
    """
    Ingestão de imagem + metadados da câmera embarcada via multipart/form-data.

    O modelo CNN roda na NVIDIA Jetson antes do envio — weather_label e confidence
    chegam já classificados pela borda. O servidor persiste e confirma imediatamente.
    """
    if image.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(status_code=422, detail="Somente JPEG e PNG são aceitos.")

    try:
        meta = json.loads(metadata)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="O campo metadata deve ser um JSON válido.")

    service = MediaService(db)
    return await service.ingest(image=image, meta=meta, device=device)
