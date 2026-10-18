from datetime import datetime

from pydantic import BaseModel


class IngestionLogResponse(BaseModel):
    """Log de auditoria de uma tentativa de ingestão (rota pública: sem a mensagem de erro interna,
    que fica só no banco)."""

    id: int
    capture_id: int
    received_at: datetime
    protocol: str
    status: str

    model_config = {"from_attributes": True}
