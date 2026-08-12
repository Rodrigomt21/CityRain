"""Ponto de entrada para subir o servidor. Lê HOST e PORT de backend/.env"""
import os
import uvicorn
from app.core.config import settings

if __name__ == "__main__":
    reload = os.getenv("ENV", "production") == "development"
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=reload,
    )
