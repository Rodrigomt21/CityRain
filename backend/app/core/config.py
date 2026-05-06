from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configurações da aplicação lidas do arquivo .env."""

    database_url: str
    test_database_url: str = ""
    upload_dir: str = "storage"
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8501"]
    max_upload_size_mb: int = 50
    api_key: str = ""

    model_config = {"env_file": ".env"}


settings = Settings()
