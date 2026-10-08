"""Banco de teste real (Postgres) migrado pelo Alembic + cliente HTTP sobre o app.

Pulado inteiro sem TEST_DATABASE_URL. Cada sessão de teste começa com o schema
zerado e migrado do zero, então a migração nova também é testada aqui.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

URL = os.environ.get("TEST_DATABASE_URL", "")
if not URL:
    pytest.skip("TEST_DATABASE_URL não definida", allow_module_level=True)

from sqlalchemy.engine import make_url  # noqa: E402

_NOME_BANCO = make_url(URL).database or ""
if "test" not in _NOME_BANCO:
    # O conftest apaga o schema inteiro: nunca rodar contra um banco que não seja de teste.
    pytest.exit(
        f"TEST_DATABASE_URL aponta para '{_NOME_BANCO}': o nome do banco precisa conter "
        "'test' (ex.: cityrain_teste) porque o schema é apagado a cada sessão.",
        returncode=2,
    )

BACKEND = Path(__file__).resolve().parents[2]
ADMIN_KEY = "admin-de-teste"

# Settings é lido no import de app.*: aponta tudo para o banco de teste antes.
os.environ["DATABASE_URL"] = URL
os.environ["ADMIN_KEY"] = ADMIN_KEY
os.environ.setdefault("UPLOAD_DIR", str(BACKEND / ".storage_teste"))

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402


def _migrar_do_zero() -> None:
    import asyncio

    async def zerar():
        eng = create_async_engine(URL, poolclass=NullPool)
        async with eng.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        await eng.dispose()

    asyncio.run(zerar())
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND,
        env={**os.environ, "DATABASE_URL": URL},
        check=True,
    )


_migrar_do_zero()

from app.core.config import settings  # noqa: E402
from app.core.database import get_db  # noqa: E402
from app.main import app  # noqa: E402

# Os testes unitários importam app.* antes deste conftest, então o objeto settings
# pode já existir sem a ADMIN_KEY e o UPLOAD_DIR de teste: fixa direto no objeto.
settings.admin_key = ADMIN_KEY
settings.upload_dir = os.environ["UPLOAD_DIR"]

_engine = create_async_engine(URL, poolclass=NullPool)
_Sessao = async_sessionmaker(_engine, expire_on_commit=False)


async def _get_db_teste():
    async with _Sessao() as s:
        yield s


app.dependency_overrides[get_db] = _get_db_teste


@pytest.fixture
async def db():
    async with _Sessao() as s:
        yield s
        await s.rollback()


@pytest.fixture
async def client():
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://teste") as c:
        yield c


@pytest.fixture
def admin_headers():
    return {"Authorization": f"Bearer {ADMIN_KEY}"}


@pytest.fixture
def criar_device(client, admin_headers):
    contador = {"n": 0}

    async def _criar(nome: str, **campos):
        contador["n"] += 1
        corpo = {"name": f"{nome}-{os.getpid()}-{contador['n']}", **campos}
        r = await client.post("/api/v1/devices/", json=corpo, headers=admin_headers)
        assert r.status_code == 201, r.text
        dados = r.json()
        return dados, dados["api_key"]

    return _criar
