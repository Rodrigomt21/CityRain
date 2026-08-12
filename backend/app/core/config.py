from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configurações da aplicação lidas do arquivo .env."""

    database_url: str
    test_database_url: str = ""
    # Pool de conexões: dimensionar para câmeras simultâneas + dashboard.
    # pool_size = conexões mantidas abertas; max_overflow = extras sob pico.
    db_pool_size: int = 10
    db_max_overflow: int = 20
    upload_dir: str = "storage"
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8501"]
    max_upload_size_mb: int = 50
    api_key: str = ""
    admin_key: str = ""
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {"env_file": ".env"}


settings = Settings()
