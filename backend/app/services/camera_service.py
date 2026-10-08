"""Consultas das câmeras fixas (tipo='fixa')."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capture import Capture
from app.models.device import Device
from app.models.media_file import MediaFile
from app.schemas.camera import CameraResumo, PontoSerie, UltimaCaptura
from app.services.capture_service import _sem_demo


class CameraService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def listar(self, excluir_demo: bool = False) -> list[CameraResumo]:
        devices = (await self.db.execute(select(Device).where(Device.tipo == "fixa").order_by(Device.name))).scalars().all()
        saida = []
        for d in devices:
            q = select(Capture).where(Capture.device_id == d.id).order_by(Capture.captured_at.desc()).limit(1)
            if excluir_demo:
                q = _sem_demo(q)
            cap = (await self.db.execute(q)).scalar_one_or_none()
            saida.append(CameraResumo(
                id=d.id, name=d.name, descricao=d.descricao, latitude=d.latitude, longitude=d.longitude,
                stream_url=d.stream_url, is_active=d.is_active, last_seen_at=d.last_seen_at,
                ultima_captura=UltimaCaptura.model_validate(cap, from_attributes=True) if cap else None,
                imagem_url=f"/api/v1/captures/{cap.id}/imagem" if cap else None,
            ))
        return saida

    async def serie(self, device_id: int, horas: int, excluir_demo: bool = False) -> Optional[list[PontoSerie]]:
        d = await self.db.get(Device, device_id)
        if d is None or d.tipo != "fixa":
            return None
        desde = datetime.now(timezone.utc) - timedelta(hours=horas)
        q = select(Capture).where(Capture.device_id == device_id, Capture.captured_at >= desde).order_by(Capture.captured_at)
        if excluir_demo:
            q = _sem_demo(q)
        caps = (await self.db.execute(q)).scalars().all()
        return [PontoSerie.model_validate(c, from_attributes=True) for c in caps]

    async def arquivo_da_captura(self, capture_id: int) -> Optional[MediaFile]:
        q = select(MediaFile).where(MediaFile.capture_id == capture_id).order_by(MediaFile.id).limit(1)
        return (await self.db.execute(q)).scalar_one_or_none()
