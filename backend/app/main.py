from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.api.router import router as api_router
from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.models import Capture, IngestionLog, MediaFile  # noqa: F401 — registra models no Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Verifica conectividade com o banco ao iniciar. Nunca altera o schema."""
    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT 1"))
    yield
    await engine.dispose()


app = FastAPI(
    title="CityRain API",
    description=(
        "API de ingestão e análise de imagens de chuva urbana capturadas por câmera "
        "embarcada em veículo conectado a uma NVIDIA Jetson.\n\n"
        "O modelo CNN roda **na própria Jetson** (borda) — `weather_label` e `confidence` "
        "chegam já classificados em cada requisição.\n\n"
        "**Para a equipe de hardware:** use `POST /api/v1/ingest` com multipart/form-data. "
        "Inclua `weather_label` e `confidence` no JSON de metadata.\n\n"
        "**Para o dashboard:** use `/api/v1/captures` e `/api/v1/stats`."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

_allow_credentials = "*" not in settings.cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health", tags=["health"])
async def health():
    """Confirma que a API está no ar."""
    return {"status": "ok"}


@app.get("/health/db", tags=["health"])
async def health_db():
    """Testa conectividade com o PostgreSQL."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as exc:
        return {"status": "error", "database": str(exc)}
