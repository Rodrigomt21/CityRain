from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class IngestionLogResponse(BaseModel):
    """Log de auditoria de uma tentativa de ingestão."""

    id: int
    capture_id: int
    received_at: datetime
    protocol: str
    status: str
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}
