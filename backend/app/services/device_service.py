import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device


# Intervalo mínimo entre atualizações de last_seen_at. Com captura a cada ~10s,
# atualizar a cada requisição geraria um commit extra por ingestão sem ganho:
# "visto há menos de 1 minuto" é precisão suficiente para monitoramento.
LAST_SEEN_THROTTLE_SECONDS = 60


def generate_api_key() -> str:
    """Gera uma chave de API aleatória de alta entropia. Nunca é armazenada."""
    return secrets.token_urlsafe(32)


def _hash_key(plaintext: str) -> str:
    """Retorna o SHA-256 hex da chave. É este hash que vai para o banco."""
    return hashlib.sha256(plaintext.encode()).hexdigest()


class DeviceService:
    """CRUD e autenticação de dispositivos embarcados."""

    def __init__(self, db: AsyncSession) -> None:
        """Inicializa o serviço com a sessão de banco da requisição."""
        self.db = db

    async def create_device(
        self,
        name: str,
        vehicle_plate: Optional[str] = None,
        hw_model: Optional[str] = None,
        metadata_: Optional[dict] = None,
    ) -> tuple[Device, str]:
        """
        Registra um novo dispositivo e retorna (device, plaintext_key).

        A chave em texto puro é retornada UMA ÚNICA VEZ — armazene-a no Jetson.
        O banco guarda apenas o hash SHA-256; a chave original não pode ser recuperada.
        """
        plaintext_key = generate_api_key()
        device = Device(
            name=name,
            vehicle_plate=vehicle_plate,
            hw_model=hw_model,
            metadata_=metadata_,
            api_key_hash=_hash_key(plaintext_key),
        )
        self.db.add(device)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(status_code=409, detail=f"Já existe um dispositivo com o nome '{name}'.")
        await self.db.refresh(device)
        return device, plaintext_key

    async def get_by_api_key_hash(self, plaintext_key: str) -> Optional[Device]:
        """Busca device pelo hash da chave recebida no header Authorization."""
        key_hash = _hash_key(plaintext_key)
        result = await self.db.execute(
            select(Device).where(Device.api_key_hash == key_hash)
        )
        return result.scalar_one_or_none()

    async def list_devices(self) -> list[Device]:
        """Lista todos os dispositivos, do mais recente ao mais antigo."""
        result = await self.db.execute(
            select(Device).order_by(Device.registered_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, device_id: int) -> Optional[Device]:
        """Busca dispositivo por ID."""
        result = await self.db.execute(
            select(Device).where(Device.id == device_id)
        )
        return result.scalar_one_or_none()

    async def deactivate(self, device_id: int) -> Optional[Device]:
        """
        Desativa o dispositivo (soft delete).

        O registro é preservado para auditoria — capturas históricas continuam vinculadas.
        """
        device = await self.get_by_id(device_id)
        if not device:
            return None
        device.is_active = False
        await self.db.commit()
        await self.db.refresh(device)
        return device

    async def update_last_seen(self, device: Device) -> None:
        """
        Atualiza o timestamp de último contato, com throttle.

        Só persiste se a última atualização tiver mais de LAST_SEEN_THROTTLE_SECONDS —
        corta o write extra por ingestão quando a câmera envia em alta frequência.
        """
        now = datetime.now(timezone.utc)
        if (
            device.last_seen_at
            and (now - device.last_seen_at).total_seconds() < LAST_SEEN_THROTTLE_SECONDS
        ):
            return
        device.last_seen_at = now
        await self.db.commit()
