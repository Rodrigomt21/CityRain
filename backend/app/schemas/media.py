from pydantic import BaseModel


class MediaFileResponse(BaseModel):
    """Arquivo de mídia vinculado a uma captura (rota pública: sem o caminho no disco do servidor)."""

    id: int
    capture_id: int
    mime_type: str
    file_name: str
    sha256: str

    model_config = {"from_attributes": True}
