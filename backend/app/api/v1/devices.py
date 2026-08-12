from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verificar_admin_key
from app.schemas.device import DeviceCreate, DeviceCreatedResponse, DeviceResponse
from app.services.device_service import DeviceService

router = APIRouter()


@router.post(
    "/",
    response_model=DeviceCreatedResponse,
    status_code=201,
    dependencies=[Depends(verificar_admin_key)],
)
async def register_device(
    body: DeviceCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Registra um novo dispositivo embarcado (Jetson) e retorna sua chave de API.

    A chave aparece APENAS nesta resposta — armazene-a no Jetson imediatamente
    (variável de ambiente ou arquivo de config). Não há como recuperá-la depois.
    """
    service = DeviceService(db)
    device, plaintext_key = await service.create_device(
        name=body.name,
        vehicle_plate=body.vehicle_plate,
        hw_model=body.hw_model,
        metadata_=body.metadata_,
    )
    return DeviceCreatedResponse(
        id=device.id,
        name=device.name,
        vehicle_plate=device.vehicle_plate,
        hw_model=device.hw_model,
        is_active=device.is_active,
        registered_at=device.registered_at,
        last_seen_at=device.last_seen_at,
        api_key=plaintext_key,
    )


@router.get(
    "/",
    response_model=list[DeviceResponse],
    dependencies=[Depends(verificar_admin_key)],
)
async def list_devices(db: AsyncSession = Depends(get_db)):
    """Lista todos os dispositivos registrados com status e último contato."""
    service = DeviceService(db)
    return await service.list_devices()


@router.delete(
    "/{device_id}",
    status_code=204,
    dependencies=[Depends(verificar_admin_key)],
)
async def deactivate_device(device_id: int, db: AsyncSession = Depends(get_db)):
    """
    Desativa o dispositivo (soft delete).

    O Jetson perde acesso imediatamente. Capturas históricas são preservadas.
    """
    service = DeviceService(db)
    device = await service.deactivate(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo não encontrado.")
