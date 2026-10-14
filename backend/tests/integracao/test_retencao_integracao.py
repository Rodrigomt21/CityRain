"""Retenção de imagens de fixa contra Postgres real."""

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import settings
from app.models.capture import Capture
from app.models.device import Device
from app.models.media_file import MediaFile
from app.services.retencao_service import limpar_imagens_fixa


async def _device(db, tipo):
    d = Device(name=f"ret-{tipo}-{os.getpid()}-{datetime.now().timestamp()}", api_key_hash=os.urandom(16).hex(),
               tipo=tipo, latitude=-23.5 if tipo == "fixa" else None, longitude=-46.6 if tipo == "fixa" else None)
    db.add(d)
    await db.flush()
    return d


async def _captura(db, device, minutos_atras, tmp_path, criar_arquivo=True):
    quando = datetime.now(timezone.utc) - timedelta(minutes=minutos_atras)
    c = Capture(captured_at=quando, received_at=quando, latitude=-23.5, longitude=-46.6,
                source_type="camera_fixa", device_id=device.id)
    db.add(c)
    await db.flush()
    arq = tmp_path / f"{c.id}.jpg"
    if criar_arquivo:
        arq.write_bytes(b"x")
    m = MediaFile(capture_id=c.id, file_path=str(arq), mime_type="image/jpeg", file_name="f.jpg",
                  sha256=os.urandom(32).hex())
    db.add(m)
    await db.commit()
    return c.id, arq


async def _media_de(db, capture_id):
    r = await db.execute(select(MediaFile).where(MediaFile.capture_id == capture_id))
    return r.scalars().all()


async def test_retencao_fixa_velha_apagada_resto_intacto(db, tmp_path):
    fixa, movel = await _device(db, "fixa"), await _device(db, "movel")
    velha, arq_velha = await _captura(db, fixa, settings.retencao_imagem_fixa_min + 5, tmp_path)
    nova, arq_nova = await _captura(db, fixa, 1, tmp_path)
    movel_velha, arq_movel = await _captura(db, movel, 10_000, tmp_path)
    sumida, _ = await _captura(db, fixa, settings.retencao_imagem_fixa_min + 5, tmp_path, criar_arquivo=False)

    await limpar_imagens_fixa(db)

    assert not arq_velha.exists() and await _media_de(db, velha) == []
    assert await _media_de(db, sumida) == []  # arquivo ausente tolerado
    assert arq_nova.exists() and len(await _media_de(db, nova)) == 1
    assert arq_movel.exists() and len(await _media_de(db, movel_velha)) == 1
    for cid in (velha, nova, movel_velha, sumida):  # histórico permanece
        assert await db.get(Capture, cid) is not None
