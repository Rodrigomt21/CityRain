from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.device import Device
from app.services.device_service import DeviceService

_bearer = HTTPBearer()


async def verificar_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> Device:
    """
    Valida Bearer token e retorna o Device correspondente.

    Fluxo:
    1. Busca o device pelo hash da chave no banco (caminho principal).
    2. Se não encontrar, tenta a chave legada de settings.api_key (retrocompatibilidade).
    3. Rejeita dispositivos inativos com 401.

    O device retornado é injetado nos endpoints via Depends() para que saibam
    qual Jetson está enviando dados.
    """
    token = credentials.credentials
    service = DeviceService(db)

    device = await service.get_by_api_key_hash(token)

    if device:
        if not device.is_active:
            raise HTTPException(status_code=401, detail="Dispositivo desativado.")
        await service.update_last_seen(device)
        return device

    # Caminho legado: chave única do .env (manter até migrar todos os Jetsons)
    if settings.api_key and token == settings.api_key:
        sentinel = Device(name="legacy", api_key_hash="", is_active=True)
        return sentinel

    raise HTTPException(status_code=401, detail="Chave de API inválida.")


async def verificar_admin_key(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> None:
    """
    Valida a chave de administração para endpoints de gerenciamento de devices.

    Admin key é estática (settings.admin_key) — usada apenas em operações de
    baixa frequência como registrar ou desativar um Jetson.
    """
    token = credentials.credentials
    if not settings.admin_key or token != settings.admin_key:
        raise HTTPException(status_code=401, detail="Chave de administração inválida.")
