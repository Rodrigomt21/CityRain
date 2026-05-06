from fastapi import Header, HTTPException

from app.core.config import settings


async def verificar_api_key(authorization: str = Header(...)) -> None:
    """
    Valida API Key no header Authorization: Bearer <chave>.
    Estrutura de dicionário preparada para múltiplos veículos futuros.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="use o token")
    chave = authorization.removeprefix("Bearer ")
    if chave != settings.api_key:
        raise HTTPException(status_code=401, detail="chave de API inválida")
