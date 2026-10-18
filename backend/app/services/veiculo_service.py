"""Consultas dos veículos (dispositivos tipo='movel')."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capture import Capture
from app.models.device import Device
from app.schemas.veiculo import UltimaCapturaVeiculo, VeiculoResumo
from app.services.capture_service import _sem_demo


class VeiculoService:
    """Lista os veículos ativos com a última captura de cada um (espelha CameraService)."""

    def __init__(self, db: AsyncSession) -> None:
        """Inicializa o serviço com a sessão de banco da requisição."""
        self.db = db

    async def listar(self, excluir_demo: bool = False) -> list[VeiculoResumo]:
        """Veículos ativos, por nome, com a última captura (por captured_at).

        Args:
            excluir_demo: ignora capturas de demonstração ao escolher a última.
        """
        q = select(Device).where(Device.tipo == "movel", Device.is_active.is_(True)).order_by(Device.name)
        devices = (await self.db.execute(q)).scalars().all()
        saida = []
        for d in devices:
            qc = select(Capture).where(Capture.device_id == d.id).order_by(Capture.captured_at.desc()).limit(1)
            if excluir_demo:
                qc = _sem_demo(qc)
            cap = (await self.db.execute(qc)).scalar_one_or_none()
            saida.append(VeiculoResumo(
                id=d.id, name=d.name, hw_model=d.hw_model, is_active=d.is_active, last_seen_at=d.last_seen_at,
                ultima_captura=UltimaCapturaVeiculo.da_captura(cap) if cap else None,
            ))
        return saida
