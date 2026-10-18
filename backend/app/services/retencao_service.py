"""Retenção de imagens de câmera fixa: apaga arquivo + MediaFile antigos, mantém o Capture."""

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.capture import Capture
from app.models.device import Device
from app.models.media_file import MediaFile

logger = logging.getLogger(__name__)

# No máximo uma varredura por minuto por processo; cada varredura apaga em lotes.
INTERVALO_S = 60.0
LOTE = 500
_ultima_execucao: Optional[float] = None


def _apagar_arquivo(caminho: str) -> None:
    """Remove o arquivo; arquivo já ausente não é erro."""
    try:
        os.remove(caminho)
    except FileNotFoundError:
        pass


async def limpar_imagens_fixa(db: AsyncSession, agora: Optional[datetime] = None) -> int:
    """
    Apaga imagens (disco + MediaFile) de capturas de câmera fixa mais antigas que
    settings.retencao_imagem_fixa_min. Capture e mídia de dispositivo móvel ficam intactos.
    Devolve quantas linhas de MediaFile foram removidas.
    """
    agora = agora or datetime.now(timezone.utc)
    limite = agora - timedelta(minutes=settings.retencao_imagem_fixa_min)
    total = 0
    while True:
        res = await db.execute(
            select(MediaFile.id, MediaFile.file_path)
            .join(Capture, Capture.id == MediaFile.capture_id)
            .join(Device, Device.id == Capture.device_id)
            .where(Device.tipo == "fixa", Capture.received_at < limite)
            .limit(LOTE)
        )
        linhas = res.all()
        if not linhas:
            break
        ids = []
        for id_, caminho in linhas:
            try:
                _apagar_arquivo(caminho)
            except OSError:
                # Não conseguiu apagar (permissão etc.): mantém a linha para tentar depois.
                logger.warning("retenção: falha ao apagar %s", caminho, exc_info=True)
                continue
            ids.append(id_)
        if ids:
            await db.execute(delete(MediaFile).where(MediaFile.id.in_(ids)))
            await db.commit()
            total += len(ids)
        if len(ids) < len(linhas) or len(linhas) < LOTE:
            break
    return total


async def rodar_uma_vez(sessao_factory: Callable[[], AsyncSession]) -> int:
    """Uma varredura com sessão própria (fora de requisição); nunca propaga erro.

    Args:
        sessao_factory: fábrica de sessões (ex.: AsyncSessionLocal).

    Returns:
        Quantas imagens foram apagadas (0 se falhou).
    """
    try:
        async with sessao_factory() as db:
            n = await limpar_imagens_fixa(db)
        if n:
            logger.info("retenção periódica: %d imagem(ns) de câmera fixa apagada(s)", n)
        return n
    except Exception:
        logger.exception("retenção periódica: falha ao limpar imagens de câmera fixa")
        return 0


async def tarefa_periodica(sessao_factory: Callable[[], AsyncSession], intervalo_s: float) -> None:
    """Roda a retenção a cada `intervalo_s`, mesmo sem ingestão (iniciada no lifespan do app).

    Sem isso, as imagens só eram apagadas quando chegava foto nova de câmera fixa: com o
    coletor parado, imagens de dias atrás continuavam públicas em /captures/{id}/imagem.
    """
    while True:
        await rodar_uma_vez(sessao_factory)
        await asyncio.sleep(intervalo_s)


async def limpar_imagens_fixa_throttled(db: AsyncSession) -> None:
    """Chamada barata do caminho de ingestão: no máximo 1x/min; nunca propaga erro."""
    global _ultima_execucao
    agora = time.monotonic()
    if _ultima_execucao is not None and agora - _ultima_execucao < INTERVALO_S:
        return
    _ultima_execucao = agora
    try:
        n = await limpar_imagens_fixa(db)
        if n:
            logger.info("retenção: %d imagem(ns) de câmera fixa apagada(s)", n)
    except Exception:
        logger.exception("retenção: falha ao limpar imagens de câmera fixa")
        try:
            await db.rollback()
        except Exception:
            pass
