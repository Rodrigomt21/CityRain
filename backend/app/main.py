import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.api.router import router as api_router
from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.models import Capture, IngestionLog, MediaFile  # noqa: F401 — registra models no Base
from app.services.retencao_service import tarefa_periodica

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Verifica conectividade com o banco ao iniciar e liga a retenção periódica. Nunca altera o schema."""
    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT 1"))
    retencao = None
    if settings.retencao_intervalo_s > 0:
        retencao = asyncio.create_task(tarefa_periodica(AsyncSessionLocal, settings.retencao_intervalo_s))
    yield
    if retencao is not None:
        retencao.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await retencao
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
        "**Câmera fixa:** dispositivo cadastrado com `tipo='fixa'`, latitude e longitude. "
        "Sempre envia a imagem (sem imagem → 422). A posição vem do cadastro. A classe vem "
        "do modelo fixo de 4 classes, que pode devolver `seco`. Use `GET /api/v1/cameras/` "
        "e `?tipo=fixa|movel` em `/captures` e `/stats/geo`.\n\n"
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


@app.exception_handler(RequestValidationError)
async def registrar_ingest_invalido(request: Request, exc: RequestValidationError):
    """Loga a ingestão recusada na validação (422) e responde como o FastAPI responderia.

    O Bearer da Jetson é aceito (e o last_seen_at atualizado) antes de o corpo ser validado:
    sem este log, uma Jetson que manda o multipart errado parecia "online" sem gravar nada.
    """
    if request.url.path.endswith("/ingest"):
        campos = [".".join(str(p) for p in e.get("loc", ())) + f": {e.get('msg')}" for e in exc.errors()]
        logger.warning("ingest recusado (422) de %s: %s", request.client.host if request.client else "?", "; ".join(campos))
    return await request_validation_exception_handler(request, exc)


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
