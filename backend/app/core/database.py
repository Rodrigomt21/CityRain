from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Classe base para todos os models SQLAlchemy do projeto."""

    pass


async def get_db() -> AsyncSession:
    """
    Dependency injection do FastAPI.
    Abre uma sessão de banco por requisição e garante o fechamento ao final.
    """
    async with AsyncSessionLocal() as session:
        yield session
