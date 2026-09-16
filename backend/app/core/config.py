import json
from typing import Annotated, Any, List

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode


class Settings(BaseSettings):
    """Configurações da aplicação lidas do arquivo .env."""

    database_url: str
    test_database_url: str = ""

    @field_validator("database_url", "test_database_url", mode="before")
    @classmethod
    def _fix_async_scheme(cls, v: str) -> str:
        # Railway fornece postgresql:// mas asyncpg exige postgresql+asyncpg://
        if v and v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    # Pool de conexões: dimensionar para câmeras simultâneas + dashboard.
    # pool_size = conexões mantidas abertas; max_overflow = extras sob pico.
    db_pool_size: int = 10
    db_max_overflow: int = 20
    upload_dir: str = "storage"
    # NoDecode: por padrão o pydantic-settings tenta fazer json.loads() em campos
    # complexos (List[str]) lidos de variável de ambiente ANTES de rodar o
    # field_validator abaixo, quebrando com JSONDecodeError se o valor não for
    # um array JSON. Com NoDecode, o valor bruto da env var vai direto pro
    # validator, que decide se é JSON ou CSV.
    cors_origins: Annotated[List[str], NoDecode] = [
        "http://localhost:3000",
        "http://localhost:8501",
    ]
    max_upload_size_mb: int = 50
    api_key: str = ""
    admin_key: str = ""
    host: str = "0.0.0.0"
    port: int = 8000

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                return json.loads(v)
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    model_config = {"env_file": ".env"}


settings = Settings()
