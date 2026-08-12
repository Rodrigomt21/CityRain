from pydantic import BaseModel


class MediaFileResponse(BaseModel):
    """Arquivo de mídia vinculado a uma captura."""

    id: int
    capture_id: int
    file_path: str
    mime_type: str
    file_name: str
    sha256: str

    model_config = {"from_attributes": True}
