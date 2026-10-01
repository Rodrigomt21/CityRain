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
        "A Jetson roda um **gate binário** (chuva/não-chuva) e decide apenas se envia "
        "a imagem. A **intensidade** (`garoa`/`moderado`/`forte`) é classificada no "
        "backend sobre a imagem recebida.\n\n"
        "**Para a equipe de hardware:** use `POST /api/v1/ingest` com multipart/form-data. "
        "Não envie `weather_label` nem `confidence` — eles são do backend. Quando o gate "
        "classificar a captura como 'sem chuva' e descartar a imagem, omita o campo "
        "`image`: o backend grava `weather_label='seco'` com `confidence` nulo.\n\n"
        "**Intensidade não medida:** enquanto nenhum modelo de intensidade estiver "
        "carregado, capturas com imagem são gravadas com `weather_label` **nulo**. Nulo "
        "significa *não medido* e é diferente de `seco`, que afirma ausência de chuva. "
        "Não renderizar um como o outro.\n\n"
        "**Para o dashboard:** use `/api/v1/captures` e `/api/v1/stats`."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

_allow_credentials = "*" in settings.cors_origins

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
