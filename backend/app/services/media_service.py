import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.capture import Capture
from app.models.device import Device
from app.models.ingestion_log import IngestionLog
from app.models.media_file import MediaFile


class MediaService:
    """Orquestra o fluxo de ingestão: valida → persiste no disco → persiste no banco."""

    def __init__(self, db: AsyncSession) -> None:
        """Inicializa o serviço com a sessão de banco da requisição."""
        self.db = db

    async def ingest(
        self,
        image: UploadFile,
        meta: dict,
        device: Optional[Device] = None,
    ) -> Capture:
        """
        Recebe imagem + metadados da Jetson e persiste no banco.

        A CNN roda na Jetson antes do envio — weather_label e confidence chegam
        já classificados pela borda. O servidor valida, persiste e confirma o recebimento.

        Fluxo em dois commits para garantir auditoria mesmo em caso de falha:
          Commit 1: apenas o Capture (ID estável para o log de erro)
          Commit 2: MediaFile + IngestionLog("success")
                    ou IngestionLog("error") se o commit 2 falhar
        """
        required = {"captured_at", "latitude", "longitude", "source_type", "weather_label", "confidence"}
        missing = required - meta.keys()
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Campos obrigatórios ausentes no metadata: {sorted(missing)}",
            )

        try:
            captured_at = datetime.fromisoformat(
                str(meta["captured_at"]).replace("Z", "+00:00")
            )
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=400,
                detail="captured_at deve ser ISO 8601. Ex: 2026-05-01T14:30:00Z",
            )

        confidence = meta["confidence"]
        if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
            raise HTTPException(
                status_code=400,
                detail="confidence deve ser um número entre 0.0 e 1.0.",
            )

        content = await image.read()
        sha256 = hashlib.sha256(content).hexdigest()

        # Commit 1: persiste o Capture antes de tentar salvar o arquivo.
        # Isso garante que capture.id existe mesmo se o commit 2 falhar,
        # permitindo que o log de erro seja vinculado a esta tentativa.
        capture = Capture(
            captured_at=captured_at,
            received_at=datetime.now(timezone.utc),
            latitude=meta["latitude"],
            longitude=meta["longitude"],
            source_type=meta["source_type"],
            weather_label=meta["weather_label"],
            confidence=float(confidence),
            metadata_=meta.get("metadata"),
            device_id=device.id if device and device.id else None,
        )
        self.db.add(capture)
        await self.db.commit()
        await self.db.refresh(capture)

        # capture_id é salvo antes do try para que o handler de erro possa usá-lo
        # sem acessar capture.id após rollback (que expiraria o objeto e causaria lazy load fora de contexto).
        capture_id = capture.id
        device_name = device.name if device else None

        # Commit 2: salva arquivo + MediaFile + IngestionLog.
        # Em caso de falha, grava IngestionLog("error") para auditoria.
        try:
            file_path = await self._save_file(
                content, sha256, image.filename or "image.jpg", capture_id, device_name
            )
            self.db.add(MediaFile(
                capture_id=capture_id,
                file_path=str(file_path),
                mime_type=image.content_type or "image/jpeg",
                file_name=image.filename or "image.jpg",
                sha256=sha256,
            ))
            self.db.add(IngestionLog(
                capture_id=capture_id,
                protocol="http_multipart",
                status="success",
            ))
            await self.db.commit()
            await self.db.refresh(capture)
            return capture

        except IntegrityError:
            await self.db.rollback()
            # expunge_all limpa o identity map — evita que objetos expirados causem lazy loads
            self.db.expunge_all()
            msg = "SHA-256 já existe: imagem duplicada."
            self.db.add(IngestionLog(
                capture_id=capture_id,
                protocol="http_multipart",
                status="error",
                error_message=msg,
            ))
            await self.db.commit()
            raise HTTPException(status_code=409, detail=msg)

        except Exception as exc:
            await self.db.rollback()
            self.db.expunge_all()
            msg = f"{type(exc).__name__}: {exc}"
            self.db.add(IngestionLog(
                capture_id=capture_id,
                protocol="http_multipart",
                status="error",
                error_message=msg[:500],
            ))
            await self.db.commit()
            raise HTTPException(status_code=500, detail="Falha ao processar a imagem.")

    async def _save_file(
        self,
        content: bytes,
        sha256: str,
        original_name: str,
        capture_id: int,
        device_name: Optional[str] = None,
    ) -> Path:
        """Persiste o arquivo em disco de forma assíncrona, organizado por device e capture_id."""
        upload_dir = Path(settings.upload_dir) / (device_name or "legacy") / str(capture_id)
        upload_dir.mkdir(parents=True, exist_ok=True)

        suffix = Path(original_name).suffix or ".jpg"
        file_path = upload_dir / f"{sha256}{suffix}"

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)

        return file_path
