# Importar todos os models aqui garante que o SQLAlchemy (e futuramente o Alembic)
# os descubra ao gerar migrações, mesmo que não estejam referenciados em outro lugar.
from app.models.device import Device
from app.models.capture import Capture
from app.models.media_file import MediaFile
from app.models.ingestion_log import IngestionLog

__all__ = ["Device", "Capture", "MediaFile", "IngestionLog"]
