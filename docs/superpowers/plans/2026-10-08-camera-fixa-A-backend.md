# Câmera fixa — Plano A: Backend

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O backend passa a distinguir dispositivo móvel (Jetson) de câmera fixa, classifica cada um com o seu modelo e expõe as câmeras fixas para o dashboard.

**Architecture:** O tipo vem do dispositivo (`devices.tipo`), nunca da imagem. O `/ingest` continua com o mesmo contrato; para dispositivo `fixa` a posição vem do cadastro e a classe vem de um segundo ONNX (4 classes, com ou sem imagem de referência seca). Cada captura grava qual modelo a classificou. Um router novo (`/api/v1/cameras`) serve a lista de câmeras, a série e a imagem.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, asyncpg, onnxruntime, Pydantic v2, pytest + pytest-asyncio + httpx (já em `requirements.txt`).

**Spec:** `docs/specs/spec-camera-fixa.md` (seções CF6 e CF8). Mapa do código: `docs/CODEBASE_MAP.md`.

## Global Constraints

- Python **3.11** no backend (`backend/.venv`, criado com `python3.11 -m venv .venv`); 3.14 quebra o SQLAlchemy 2.0.37.
- Comentários e docstrings em português; nomes de código em inglês no backend (padrão atual dos arquivos).
- Rótulo nulo = "não medido", nunca "seco". Nenhuma tarefa pode converter um no outro.
- Vocabulário do banco: `seco`, `garoa`, `moderado`, `forte` (o ML usa `moderada`; traduzir na leitura do ONNX).
- Dispositivos existentes continuam `movel` sem nenhuma ação (default no banco).
- Migração nova é `0004`, `down_revision = "0003"`, id escrito à mão (padrão do repo).
- Commits `tipo: descrição` em português, terminando com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Não fazer push nem merge: o orquestrador integra.

## Review Focus

1. **Câmera fixa enviando sem imagem** → 422 com mensagem clara; nunca gravar `seco` em nome da câmera (Task 4).
2. **Câmera fixa enviando lat/lon no JSON diferente do cadastro** → vale o cadastro; a captura fica onde a câmera está (Task 4).
3. **Modelo fixo ausente ou quebrado no deploy** → captura gravada com rótulo nulo, ingestão segue com 201, modelo móvel não é afetado (Task 3).
4. **Modelo com referência e sem arquivo de referência para a câmera** → rótulo nulo e log de aviso, sem 500 (Task 3).
5. **Imagem de captura apagada do disco (Railway sem volume)** → `GET /captures/{id}/imagem` responde 404 e `/cameras` continua respondendo (Task 6).

---

## File Structure

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `backend/alembic/versions/0004_camera_fixa.py` | criar | colunas `devices.tipo/latitude/longitude/stream_url/descricao`, `captures.modelo/modelo_versao`, CHECK do tipo |
| `backend/app/models/device.py` | modificar | novas colunas |
| `backend/app/models/capture.py` | modificar | `modelo`, `modelo_versao` |
| `backend/app/core/config.py` | modificar | `inference_model_fixa_path`, `referencias_dir` |
| `backend/app/services/inference_service.py` | modificar | `Classificacao`, suporte a 4 classes e a entrada de 6 canais, roteador por tipo |
| `backend/app/services/periodo.py` | criar | `periodo_local(datetime) -> "dia" \| "noite"` |
| `backend/app/services/media_service.py` | modificar | regras de câmera fixa no ingest |
| `backend/app/schemas/device.py` | modificar | campos novos e validação |
| `backend/app/services/device_service.py` | modificar | persistir campos novos |
| `backend/app/api/v1/devices.py` | modificar | repassar campos novos |
| `backend/app/services/capture_service.py` | modificar | filtro `tipo` |
| `backend/app/api/v1/captures.py`, `stats.py` | modificar | parâmetro `tipo`; rota `/{id}/imagem` |
| `backend/app/schemas/camera.py` | criar | `CameraResumo`, `UltimaCaptura`, `PontoSerie` |
| `backend/app/services/camera_service.py` | criar | consultas das câmeras |
| `backend/app/api/v1/cameras.py` | criar | `GET /cameras/`, `GET /cameras/{id}/serie` |
| `backend/app/api/router.py` | modificar | registrar `cameras` |
| `backend/tests/integracao/conftest.py` | criar | banco de teste com `alembic upgrade head` e cliente ASGI |
| `backend/tests/integracao/test_*.py` | criar | testes de integração |
| `backend/tests/test_*.py` | criar | testes unitários |
| `.github/workflows/ci.yml` | modificar | serviço Postgres no job do backend |

---

### Task 1: Infraestrutura de teste com Postgres real

Hoje o backend não tem nenhum teste com banco. Esta tarefa cria a base que as tarefas 2 a 7 usam: um banco de teste migrado pelo próprio Alembic (o que também testa a migração) e um cliente HTTP sobre o app.

**Files:**
- Create: `backend/tests/integracao/__init__.py` (vazio)
- Create: `backend/tests/integracao/conftest.py`
- Create: `backend/tests/integracao/test_infra.py`
- Modify: `backend/pytest.ini` (criar)
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Produces: fixtures `client` (`httpx.AsyncClient` sobre o app, com `get_db` apontando para o banco de teste), `db` (`AsyncSession` do banco de teste), `admin_headers` (`dict` com `Authorization: Bearer <ADMIN_KEY de teste>`), `criar_device` (coroutine `async (nome, **campos) -> (dict resposta, str api_key)`).
- Variável de ambiente: `TEST_DATABASE_URL` (ex.: `postgresql+asyncpg://cityrain:cityrain@localhost:5433/cityrain_teste`). Sem ela, todos os testes de `tests/integracao/` são pulados.

- [ ] **Step 1: Subir um Postgres local para os testes**

```bash
open -a OrbStack   # se o docker não responder
docker run -d --name cityrain-pg-teste -e POSTGRES_USER=cityrain -e POSTGRES_PASSWORD=cityrain \
  -e POSTGRES_DB=cityrain_teste -p 5433:5432 postgres:16
export TEST_DATABASE_URL=postgresql+asyncpg://cityrain:cityrain@localhost:5433/cityrain_teste
```

Se o container já existir: `docker start cityrain-pg-teste`.

- [ ] **Step 2: Criar `backend/pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
asyncio_default_fixture_loop_scope = session
asyncio_default_test_loop_scope = session
```

- [ ] **Step 3: Escrever o teste que falha** (`backend/tests/integracao/test_infra.py`)

```python
"""A infraestrutura de integração sobe o app contra o banco de teste migrado."""


async def test_health_db_conecta_no_banco_de_teste(client):
    r = await client.get("/health/db")
    assert r.status_code == 200
    assert r.json()["database"] == "connected"


async def test_admin_cria_device_e_recebe_chave(criar_device):
    corpo, chave = await criar_device("teste-infra")
    assert corpo["name"].startswith("teste-infra")
    assert len(chave) > 20
```

- [ ] **Step 4: Rodar e ver falhar**

Run: `cd backend && .venv/bin/python -m pytest -q tests/integracao/test_infra.py`
Expected: ERROR `fixture 'client' not found`.

- [ ] **Step 5: Escrever `backend/tests/integracao/conftest.py`**

```python
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
```

O `httpx.ASGITransport` não roda o `lifespan` do app, e é isso que queremos (o lifespan usa o engine de produção).

- [ ] **Step 6: Rodar e ver passar**

Run: `cd backend && TEST_DATABASE_URL=$TEST_DATABASE_URL .venv/bin/python -m pytest -q tests/integracao/test_infra.py`
Expected: `2 passed`. Na sequência, `cd backend && .venv/bin/python -m pytest -q tests` sem a variável deve mostrar os testes antigos passando e os de integração como `skipped`.

O fixture `criar_device` acrescenta um sufixo ao nome (para os testes não colidirem entre execuções), então no Step 3 a asserção certa é `assert corpo["name"].startswith("teste-infra")`.

- [ ] **Step 7: Postgres no CI** (`.github/workflows/ci.yml`, job `backend`)

```yaml
  backend:
    name: Backend (pytest)
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: cityrain
          POSTGRES_PASSWORD: cityrain
          POSTGRES_DB: cityrain_teste
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U cityrain" --health-interval 5s --health-timeout 5s --health-retries 10
    env:
      TEST_DATABASE_URL: postgresql+asyncpg://cityrain:cityrain@localhost:5432/cityrain_teste
```

Manter os `steps` existentes do job. O pytest roda da raiz do repo no CI (`python -m pytest -q backend/tests`); garantir que o `pytest.ini` é encontrado: trocar o comando do CI para `cd backend && python -m pytest -q tests`.

- [ ] **Step 8: Commit**

```bash
git add backend/pytest.ini backend/tests/integracao .github/workflows/ci.yml
git commit -m "test(backend): integração com Postgres real migrado pelo Alembic"
```

---

### Task 2: Migração 0004 e modelos

**Files:**
- Create: `backend/alembic/versions/0004_camera_fixa.py`
- Modify: `backend/app/models/device.py`
- Modify: `backend/app/models/capture.py`
- Test: `backend/tests/integracao/test_migracao_0004.py`

**Interfaces:**
- Produces: `Device.tipo: str` (`"movel"` | `"fixa"`), `Device.latitude: Optional[float]`, `Device.longitude: Optional[float]`, `Device.stream_url: Optional[str]`, `Device.descricao: Optional[str]`, `Capture.modelo: Optional[str]`, `Capture.modelo_versao: Optional[str]`. Constante `DEVICE_TIPOS = ("movel", "fixa")` em `app/models/device.py`.

- [ ] **Step 1: Escrever o teste que falha** (`backend/tests/integracao/test_migracao_0004.py`)

```python
"""Migração 0004: tipo do dispositivo e modelo da captura."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


async def test_colunas_novas_existem(db):
    cols = (await db.execute(text(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_name IN ('devices', 'captures')"
    ))).all()
    nomes = {(t, c) for t, c in cols}
    for esperado in [("devices", "tipo"), ("devices", "latitude"), ("devices", "longitude"),
                     ("devices", "stream_url"), ("devices", "descricao"),
                     ("captures", "modelo"), ("captures", "modelo_versao")]:
        assert esperado in nomes


async def test_device_sem_tipo_vira_movel(db):
    await db.execute(text(
        "INSERT INTO devices (name, api_key_hash, is_active) VALUES ('legado-0004', 'h0004', true)"
    ))
    tipo = (await db.execute(text("SELECT tipo FROM devices WHERE name = 'legado-0004'"))).scalar_one()
    await db.rollback()
    assert tipo == "movel"


async def test_tipo_invalido_e_recusado(db):
    with pytest.raises(IntegrityError):
        await db.execute(text(
            "INSERT INTO devices (name, api_key_hash, is_active, tipo) VALUES ('x-0004', 'hx0004', true, 'drone')"
        ))
    await db.rollback()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && .venv/bin/python -m pytest -q tests/integracao/test_migracao_0004.py`
Expected: FAIL em `test_colunas_novas_existem` (colunas ausentes).

- [ ] **Step 3: Escrever a migração** (`backend/alembic/versions/0004_camera_fixa.py`)

```python
"""câmera fixa: tipo do dispositivo e modelo que classificou a captura

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-08 00:00:00.000000

O tipo vem do dispositivo, nunca da imagem: 'movel' (Jetson no carro, gate na
placa + modelo móvel no backend) ou 'fixa' (câmera parada, sem Jetson, modelo
fixo de 4 classes). Dispositivos existentes viram 'movel' pelo server_default.
Câmera fixa guarda a posição no cadastro (latitude/longitude) e a URL pública
de onde vem a imagem.

captures.modelo/modelo_versao registram qual ONNX classificou cada captura,
para as métricas por modelo nunca misturarem os dois domínios.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("tipo", sa.String(length=10), nullable=False, server_default="movel"))
    op.add_column("devices", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("devices", sa.Column("longitude", sa.Float(), nullable=True))
    op.add_column("devices", sa.Column("stream_url", sa.String(length=500), nullable=True))
    op.add_column("devices", sa.Column("descricao", sa.String(length=200), nullable=True))
    op.create_check_constraint("ck_devices_tipo", "devices", "tipo IN ('movel', 'fixa')")
    op.create_index("ix_devices_tipo", "devices", ["tipo"])
    op.add_column("captures", sa.Column("modelo", sa.String(length=100), nullable=True))
    op.add_column("captures", sa.Column("modelo_versao", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("captures", "modelo_versao")
    op.drop_column("captures", "modelo")
    op.drop_index("ix_devices_tipo", table_name="devices")
    op.drop_constraint("ck_devices_tipo", "devices", type_="check")
    for col in ("descricao", "stream_url", "longitude", "latitude", "tipo"):
        op.drop_column("devices", col)
```

- [ ] **Step 4: Atualizar os modelos**

Em `backend/app/models/device.py`, acrescentar `CheckConstraint, Float` aos imports do SQLAlchemy, a constante antes da classe e as colunas depois de `metadata_`:

```python
# 'movel' = Jetson no carro; 'fixa' = câmera parada sem Jetson. Alterar exige migration (CHECK).
DEVICE_TIPOS = ("movel", "fixa")
```

```python
    __table_args__ = (CheckConstraint("tipo IN ('movel', 'fixa')", name="ck_devices_tipo"),)
```

```python
    tipo: Mapped[str] = mapped_column(String(10), default="movel", server_default="movel", index=True)
    # Só para câmera fixa: posição permanente e origem pública da imagem.
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stream_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    descricao: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
```

Em `backend/app/models/capture.py`, depois de `confidence`:

```python
    # Qual ONNX classificou (metadata `experimento` e `epoca` do arquivo). Nulo quando
    # não houve inferência (captura sem imagem ou sem modelo carregado).
    modelo: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    modelo_versao: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
```

- [ ] **Step 5: Rodar e ver passar**

Run: `cd backend && .venv/bin/python -m pytest -q tests/integracao/`
Expected: todos passam. Conferir também o downgrade:
`cd backend && DATABASE_URL=$TEST_DATABASE_URL .venv/bin/alembic downgrade 0003 && DATABASE_URL=$TEST_DATABASE_URL .venv/bin/alembic upgrade head` → sem erro.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/0004_camera_fixa.py backend/app/models backend/tests/integracao/test_migracao_0004.py
git commit -m "feat(backend): migração 0004 com tipo do dispositivo e modelo da captura"
```

---

### Task 3: Inferência com dois modelos e imagem de referência

**Files:**
- Create: `backend/app/services/periodo.py`
- Modify: `backend/app/services/inference_service.py`
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/test_periodo.py`, `backend/tests/test_roteador_inferencia.py`

**Interfaces:**
- Produces:
  - `periodo_local(quando: datetime) -> Literal["dia", "noite"]` (dia = [06:00, 18:30) em UTC−3, igual a `ml/scripts/rotulagem/gerar_manifest.py`).
  - `Classificacao(NamedTuple)`: `label: Optional[str]`, `confianca: Optional[float]`, `modelo: Optional[str]`, `versao: Optional[str]`. `Classificacao.vazia()` devolve tudo `None`.
  - `InferenceService.classificar(image_bytes: bytes, referencia_bytes: Optional[bytes] = None) -> Classificacao` (async). `classify` continua existindo e devolvendo `(label, confianca)`.
  - `InferenceService.exige_referencia: bool`.
  - `RoteadorInferencia(movel: InferenceService, fixa: InferenceService, referencias_dir: Path)` com `async classificar(image_bytes, tipo: str, device_name: Optional[str], quando: datetime) -> Classificacao`.
  - Singleton `roteador_inferencia` no fim de `inference_service.py`.
  - Settings: `inference_model_fixa_path: str = ""` (vazio = `app/inference/modelos/intensidade_fixa.onnx`), `referencias_dir: str = ""` (vazio = `app/inference/referencias`).
- Contrato do ONNX fixo (produzido pelo Plano C, Task 7): metadata `classes` (JSON, pode conter `seco`), `altura`, `largura`, `media`, `desvio`, `experimento`, `epoca`, e opcionalmente `canais_entrada` (`"3"` ou `"6"`). Com 6 canais, a entrada é `concat([imagem, referencia])` no eixo dos canais, cada metade pré-processada igual.
- Referências: `<referencias_dir>/<device_name>/<periodo>.jpg`; se faltar o período pedido, usa o outro; se faltar os dois, sem referência.

- [ ] **Step 1: Testes que falham — período** (`backend/tests/test_periodo.py`)

```python
"""Dia/noite no horário local, com a mesma regra da rotulagem do ML."""

from datetime import datetime, timezone

from app.services.periodo import periodo_local


def utc(h, m=0):
    return datetime(2026, 10, 8, h, m, tzinfo=timezone.utc)


def test_meio_dia_local_e_dia():
    assert periodo_local(utc(15)) == "dia"        # 12:00 em SP


def test_limites_do_dia():
    assert periodo_local(utc(9, 0)) == "dia"      # 06:00 local, inclusivo
    assert periodo_local(utc(8, 59)) == "noite"
    assert periodo_local(utc(21, 29)) == "dia"    # 18:29 local
    assert periodo_local(utc(21, 30)) == "noite"  # 18:30 local, exclusivo


def test_data_sem_fuso_e_tratada_como_utc():
    assert periodo_local(datetime(2026, 10, 8, 15, 0)) == "dia"
```

- [ ] **Step 2: Testes que falham — roteador** (`backend/tests/test_roteador_inferencia.py`)

Os testes geram ONNX pequenos na hora (sem depender do modelo real) com `onnx.helper`. Acrescentar `onnx==1.17.0` ao `backend/requirements.txt` só se ele ainda não estiver instalado como dependência do onnxruntime; conferir com `.venv/bin/python -c "import onnx"`. Se faltar, acrescentar `onnx==1.17.0` em um `backend/requirements-dev.txt` novo e instalar no CI (`pip install -r backend/requirements.txt -r backend/requirements-dev.txt`).

```python
"""Roteamento de inferência por tipo de dispositivo, com ONNX de brinquedo."""

import asyncio
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper
from PIL import Image

from app.services.inference_service import Classificacao, InferenceService, RoteadorInferencia


def _onnx(caminho: Path, classes: list[str], canais: int, vencedora: int, experimento: str) -> Path:
    """Modelo que ignora a imagem e devolve logits com `vencedora` no topo."""
    k = len(classes)
    logits = np.full((1, k), -5.0, dtype=np.float32)
    logits[0, vencedora] = 5.0
    entrada = helper.make_tensor_value_info("imagem", TensorProto.FLOAT, ["n", canais, 8, 8])
    saida = helper.make_tensor_value_info("logits", TensorProto.FLOAT, ["n", k])
    # ReduceMean(imagem) * 0 + logits: usa a entrada (o runtime exige) sem mudar a saída
    nos = [
        helper.make_node("ReduceMean", ["imagem"], ["m"], axes=[1, 2, 3], keepdims=0),
        helper.make_node("Mul", ["m", "zero"], ["m0"]),
        helper.make_node("Unsqueeze", ["m0", "eixo"], ["m1"]),
        helper.make_node("Add", ["m1", "base"], ["logits"]),
    ]
    inits = [
        helper.make_tensor("zero", TensorProto.FLOAT, [], [0.0]),
        helper.make_tensor("eixo", TensorProto.INT64, [1], [1]),
        helper.make_tensor("base", TensorProto.FLOAT, [1, k], logits.flatten().tolist()),
    ]
    g = helper.make_graph(nos, "brinquedo", [entrada], [saida], inits)
    m = helper.make_model(g, opset_imports=[helper.make_opsetid("", 13)])
    meta = {"classes": json.dumps(classes), "altura": "8", "largura": "8",
            "media": json.dumps([0.5, 0.5, 0.5]), "desvio": json.dumps([0.5, 0.5, 0.5]),
            "experimento": experimento, "epoca": "7"}
    if canais != 3:
        meta["canais_entrada"] = str(canais)
    for chave, valor in meta.items():
        p = m.metadata_props.add()
        p.key, p.value = chave, valor
    onnx.save(m, caminho)
    return caminho


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 24), (120, 130, 140)).save(buf, "JPEG")
    return buf.getvalue()


QUANDO = datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc)  # dia


def _roteador(tmp_path, canais_fixa=3, com_referencia=True):
    movel = InferenceService(_onnx(tmp_path / "m.onnx", ["garoa", "moderada", "forte"], 3, 2, "movel_v3"))
    fixa = InferenceService(_onnx(tmp_path / "f.onnx", ["seco", "garoa", "moderada", "forte"], canais_fixa, 0, "fixa_f1"))
    refs = tmp_path / "refs"
    if com_referencia:
        (refs / "fixa-cam1").mkdir(parents=True)
        (refs / "fixa-cam1" / "noite.jpg").write_bytes(_jpeg())
    return RoteadorInferencia(movel, fixa, refs)


def test_movel_usa_modelo_movel(tmp_path):
    c = asyncio.run(_roteador(tmp_path).classificar(_jpeg(), "movel", "jetson-1", QUANDO))
    assert c.label == "forte" and c.modelo == "movel_v3" and c.versao == "ep7"


def test_fixa_usa_modelo_fixo_e_pode_devolver_seco(tmp_path):
    c = asyncio.run(_roteador(tmp_path).classificar(_jpeg(), "fixa", "fixa-cam1", QUANDO))
    assert c.label == "seco" and c.modelo == "fixa_f1"


def test_moderada_do_ml_vira_moderado_do_banco(tmp_path):
    s = InferenceService(_onnx(tmp_path / "x.onnx", ["seco", "garoa", "moderada", "forte"], 3, 2, "x"))
    assert asyncio.run(s.classificar(_jpeg())).label == "moderado"


def test_fixa_com_seis_canais_usa_referencia_do_outro_periodo_quando_falta(tmp_path):
    r = _roteador(tmp_path, canais_fixa=6)   # só existe noite.jpg; QUANDO é dia
    c = asyncio.run(r.classificar(_jpeg(), "fixa", "fixa-cam1", QUANDO))
    assert c.label == "seco"


def test_fixa_com_seis_canais_sem_referencia_fica_nao_medida(tmp_path):
    r = _roteador(tmp_path, canais_fixa=6, com_referencia=False)
    assert asyncio.run(r.classificar(_jpeg(), "fixa", "fixa-cam1", QUANDO)) == Classificacao.vazia()


def test_modelo_fixo_ausente_nao_afeta_o_movel(tmp_path):
    movel = InferenceService(_onnx(tmp_path / "m.onnx", ["garoa", "moderada", "forte"], 3, 1, "movel_v3"))
    r = RoteadorInferencia(movel, InferenceService(tmp_path / "nao_existe.onnx"), tmp_path)
    assert asyncio.run(r.classificar(_jpeg(), "fixa", "fixa-cam1", QUANDO)) == Classificacao.vazia()
    assert asyncio.run(r.classificar(_jpeg(), "movel", "j", QUANDO)).label == "moderado"


def test_classify_antigo_continua_devolvendo_par(tmp_path):
    s = InferenceService(_onnx(tmp_path / "m.onnx", ["garoa", "moderada", "forte"], 3, 0, "v3"))
    label, conf = asyncio.run(s.classify(_jpeg()))
    assert label == "garoa" and 0 < conf <= 1
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_periodo.py tests/test_roteador_inferencia.py`
Expected: FAIL com `ModuleNotFoundError: app.services.periodo` e `ImportError: Classificacao`.

- [ ] **Step 4: Implementar `backend/app/services/periodo.py`**

```python
"""Dia ou noite no horário local (UTC−3, Brasil sem horário de verão desde 2019).

Mesma regra de ``ml/scripts/rotulagem/gerar_manifest.py``: dia = [06:00, 18:30).
As imagens de referência seca são escolhidas por período, então treino e
backend precisam concordar exatamente nesta fronteira.
"""

from datetime import datetime, time, timedelta, timezone
from typing import Literal

FUSO_LOCAL = timezone(timedelta(hours=-3))
INICIO_DIA = time(6, 0)
FIM_DIA = time(18, 30)


def periodo_local(quando: datetime) -> Literal["dia", "noite"]:
    """'dia' ou 'noite' para um instante; sem fuso, assume UTC."""
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=timezone.utc)
    hora = quando.astimezone(FUSO_LOCAL).time()
    return "dia" if INICIO_DIA <= hora < FIM_DIA else "noite"
```

- [ ] **Step 5: Implementar o novo `inference_service.py`**

Substituir as partes indicadas, mantendo o resto do arquivo:

```python
from datetime import datetime
from typing import NamedTuple, Optional

# Vocabulário do ML -> vocabulário do banco. O ML usa "moderada"; o banco, "moderado".
_ML_PARA_BANCO = {"seco": "seco", "garoa": "garoa", "moderada": "moderado", "moderado": "moderado", "forte": "forte"}

MODELOS_DIR = Path(__file__).resolve().parent.parent / "inference" / "modelos"
MODELO_PADRAO = MODELOS_DIR / "intensidade.onnx"
MODELO_FIXA_PADRAO = MODELOS_DIR / "intensidade_fixa.onnx"
REFERENCIAS_PADRAO = Path(__file__).resolve().parent.parent / "inference" / "referencias"


class Classificacao(NamedTuple):
    """Resultado de uma inferência. Tudo None = intensidade não medida."""

    label: Optional[str]
    confianca: Optional[float]
    modelo: Optional[str]
    versao: Optional[str]

    @classmethod
    def vazia(cls) -> "Classificacao":
        return cls(None, None, None, None)
```

Em `_ModeloOnnx.__init__`, depois de ler `desvio`:

```python
        self.canais = int(meta.get("canais_entrada", "3"))
        self.experimento = meta.get("experimento")
        self.versao = f"ep{meta['epoca']}" if meta.get("epoca") else None
```

Trocar `preparar` e `prever`:

```python
    def _uma(self, image_bytes: bytes):
        """Igual a ``cityrain_ml.data.intensidade.preparar``: RGB -> resize bilinear -> /255 -> ImageNet."""
        from PIL import Image

        np = self._np
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize((self.largura, self.altura), Image.BILINEAR)
        x = np.asarray(img, dtype=np.float32) / 255.0
        x = (x - self.media) / self.desvio
        return x.transpose(2, 0, 1)

    def preparar(self, image_bytes: bytes, referencia_bytes: Optional[bytes] = None):
        """Tensor 1×C×H×W; com 6 canais, imagem e referência concatenadas nos canais."""
        np = self._np
        partes = [self._uma(image_bytes)]
        if self.canais == 6:
            if referencia_bytes is None:
                raise ValueError("modelo de 6 canais exige imagem de referência")
            partes.append(self._uma(referencia_bytes))
        return np.ascontiguousarray(np.concatenate(partes, axis=0))[None]

    def prever(self, image_bytes: bytes, referencia_bytes: Optional[bytes] = None) -> tuple[str, float]:
        np = self._np
        logits = self.sessao.run(None, {self.entrada: self.preparar(image_bytes, referencia_bytes)})[0][0]
        p = np.exp(logits - logits.max())
        p /= p.sum()
        k = int(p.argmax())
        return self.classes[k], float(p[k])
```

Em `InferenceService`, acrescentar:

```python
    @property
    def exige_referencia(self) -> bool:
        """True quando o modelo carregado espera imagem + referência seca (6 canais)."""
        return self._model is not None and self._model.canais == 6

    async def classificar(self, image_bytes: bytes, referencia_bytes: Optional[bytes] = None) -> Classificacao:
        """Como ``classify``, devolvendo também qual modelo classificou."""
        if self._model is None:
            if not self._avisou_sem_modelo:
                logger.warning("Nenhum modelo carregado — capturas ficam com weather_label=None (não medido).")
                self._avisou_sem_modelo = True
            return Classificacao.vazia()
        if self.exige_referencia and referencia_bytes is None:
            logger.warning("Modelo %s exige referência e nenhuma foi encontrada", self._model.experimento)
            return Classificacao.vazia()
        try:
            label, conf = await asyncio.to_thread(self._model.prever, image_bytes, referencia_bytes)
        except Exception:  # noqa: BLE001 — imagem corrompida vira "não medida", não 500
            logger.exception("Falha ao classificar imagem (%d bytes)", len(image_bytes))
            return Classificacao.vazia()
        return Classificacao(label, conf, self._model.experimento, self._model.versao)
```

Reescrever `classify` para delegar (mantém a assinatura antiga):

```python
    async def classify(self, image_bytes: bytes) -> tuple[Optional[str], Optional[float]]:
        """Compatibilidade: (weather_label, confidence). Ver ``classificar``."""
        c = await self.classificar(image_bytes)
        return c.label, c.confianca
```

No `carregar`, aceitar o caminho padrão por parâmetro para servir aos dois modelos:

```python
    def __init__(self, caminho_modelo: Optional[Path] = None, padrao: Path = MODELO_PADRAO, config_attr: str = "inference_model_path") -> None:
        self._model: Optional[_ModeloOnnx] = None
        self._avisou_sem_modelo = False
        self._padrao, self._config_attr = padrao, config_attr
        self.carregar(caminho_modelo)

    def carregar(self, caminho_modelo: Optional[Path] = None) -> None:
        """Carrega o .onnx; qualquer falha deixa o serviço sem modelo (intensidade nula), sem derrubar o app."""
        from app.core.config import settings

        caminho = Path(caminho_modelo or getattr(settings, self._config_attr) or self._padrao)
        # ... resto igual
```

No fim do arquivo, o roteador e os singletons:

```python
class RoteadorInferencia:
    """Escolhe o modelo pelo tipo do dispositivo e, para câmera fixa, a referência seca."""

    def __init__(self, movel: InferenceService, fixa: InferenceService, referencias_dir: Path) -> None:
        self.movel, self.fixa, self.referencias_dir = movel, fixa, Path(referencias_dir)

    def referencia(self, device_name: Optional[str], quando: datetime) -> Optional[bytes]:
        """``<dir>/<device>/<periodo>.jpg``; cai para o outro período se faltar."""
        from app.services.periodo import periodo_local

        if not device_name:
            return None
        pasta = self.referencias_dir / device_name
        periodo = periodo_local(quando)
        for p in (periodo, "noite" if periodo == "dia" else "dia"):
            arq = pasta / f"{p}.jpg"
            if arq.is_file():
                return arq.read_bytes()
        return None

    async def classificar(self, image_bytes: bytes, tipo: str, device_name: Optional[str], quando: datetime) -> Classificacao:
        if tipo != "fixa":
            return await self.movel.classificar(image_bytes)
        ref = self.referencia(device_name, quando) if self.fixa.exige_referencia else None
        return await self.fixa.classificar(image_bytes, ref)


def _referencias_dir() -> Path:
    from app.core.config import settings

    return Path(settings.referencias_dir) if settings.referencias_dir else REFERENCIAS_PADRAO


# Singletons: uma instância compartilhada por todas as requisições.
inference_service = InferenceService()
inference_service_fixa = InferenceService(padrao=MODELO_FIXA_PADRAO, config_attr="inference_model_fixa_path")
roteador_inferencia = RoteadorInferencia(inference_service, inference_service_fixa, _referencias_dir())
```

Atualizar a docstring do módulo e o comentário de `RAIN_LABELS`: o modelo fixo pode devolver `seco`; o móvel não.

Em `backend/app/core/config.py`, abaixo de `inference_model_path`:

```python
    # Modelo da câmera fixa (4 classes); vazio = app/inference/modelos/intensidade_fixa.onnx
    inference_model_fixa_path: str = ""
    # Referências secas por câmera: <dir>/<device_name>/{dia,noite}.jpg; vazio = app/inference/referencias
    referencias_dir: str = ""
```

- [ ] **Step 6: Rodar e ver passar**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_periodo.py tests/test_roteador_inferencia.py tests/test_inference_service.py`
Expected: todos passam (os testes antigos do modelo real continuam verdes).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/periodo.py backend/app/services/inference_service.py backend/app/core/config.py backend/tests/test_periodo.py backend/tests/test_roteador_inferencia.py backend/requirements*.txt
git commit -m "feat(backend): roteador de inferência com modelo fixo e referência seca"
```

---

### Task 4: Cadastro de câmera fixa e regras no ingest

**Files:**
- Modify: `backend/app/schemas/device.py`, `backend/app/services/device_service.py`, `backend/app/api/v1/devices.py`
- Modify: `backend/app/services/media_service.py`
- Test: `backend/tests/integracao/test_ingest_fixa.py`

**Interfaces:**
- Consumes: `roteador_inferencia.classificar(image_bytes, tipo, device_name, quando) -> Classificacao` (Task 3); colunas da Task 2.
- Produces:
  - `DeviceCreate` com `tipo: Literal["movel","fixa"] = "movel"`, `latitude`, `longitude` (`Optional[float]`, faixas válidas), `stream_url: Optional[str]` (≤ 500), `descricao: Optional[str]` (≤ 200). Validador: `tipo == "fixa"` exige `latitude` e `longitude`.
  - `DeviceResponse` e `DevicePublico` ganham `tipo`, `latitude`, `longitude`, `stream_url`, `descricao`.
  - `CaptureResponse` ganha `modelo: Optional[str]`, `modelo_versao: Optional[str]`.
  - `DeviceService.create_device(..., tipo="movel", latitude=None, longitude=None, stream_url=None, descricao=None)`.
  - Regras do ingest para `device.tipo == "fixa"`: imagem obrigatória (422), `latitude`/`longitude` do cadastro (as do JSON são opcionais e ignoradas), `source_type = "camera_fixa"`.

- [ ] **Step 1: Escrever os testes que falham** (`backend/tests/integracao/test_ingest_fixa.py`)

```python
"""Ingestão de câmera fixa: posição do cadastro, imagem obrigatória, modelo registrado."""

import io
import json

from PIL import Image

from app.services import inference_service as inf
from app.services.inference_service import Classificacao


def _jpeg(cor=(100, 110, 120)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), cor).save(buf, "JPEG")
    return buf.getvalue()


def _meta(**kw):
    base = {"captured_at": "2026-10-08T15:00:00Z", "source_type": "qualquer"}
    return {"metadata": json.dumps({**base, **kw})}


async def _fixa(criar_device):
    return await criar_device("fixa-cam", tipo="fixa", latitude=-23.5465, longitude=-46.6340,
                              stream_url="https://youtube.com/watch?v=x", descricao="Centro de SP")


async def test_cadastro_de_fixa_exige_posicao(client, admin_headers):
    r = await client.post("/api/v1/devices/", json={"name": "fixa-sem-pos", "tipo": "fixa"}, headers=admin_headers)
    assert r.status_code == 422


async def test_cadastro_devolve_tipo_e_posicao(criar_device):
    corpo, _ = await _fixa(criar_device)
    assert corpo["tipo"] == "fixa" and corpo["latitude"] == -23.5465


async def test_fixa_sem_imagem_e_recusada(client, criar_device):
    _, chave = await _fixa(criar_device)
    r = await client.post("/api/v1/ingest", data=_meta(), headers={"Authorization": f"Bearer {chave}"})
    assert r.status_code == 422
    assert "imagem" in r.json()["detail"].lower()


async def test_fixa_usa_posicao_do_cadastro_e_registra_modelo(client, criar_device, monkeypatch):
    async def falso(image_bytes, tipo, device_name, quando):
        assert tipo == "fixa"
        return Classificacao("moderado", 0.81, "fixa_f3", "ep7")

    monkeypatch.setattr(inf.roteador_inferencia, "classificar", falso)
    _, chave = await _fixa(criar_device)
    r = await client.post(
        "/api/v1/ingest",
        data=_meta(latitude=0.0, longitude=0.0),
        files={"image": ("f.jpg", _jpeg((1, 2, 3)), "image/jpeg")},
        headers={"Authorization": f"Bearer {chave}"},
    )
    assert r.status_code == 201, r.text
    c = r.json()
    assert (c["latitude"], c["longitude"]) == (-23.5465, -46.6340)
    assert c["source_type"] == "camera_fixa"
    assert (c["weather_label"], c["modelo"], c["modelo_versao"]) == ("moderado", "fixa_f3", "ep7")


async def test_movel_continua_exigindo_lat_lon_do_json(client, criar_device):
    _, chave = await criar_device("jetson")
    r = await client.post("/api/v1/ingest", data=_meta(), headers={"Authorization": f"Bearer {chave}"})
    assert r.status_code == 400


async def test_movel_sem_imagem_continua_seco(client, criar_device):
    _, chave = await criar_device("jetson-seco")
    r = await client.post("/api/v1/ingest", data=_meta(latitude=-23.5, longitude=-46.6),
                          headers={"Authorization": f"Bearer {chave}"})
    assert r.status_code == 201 and r.json()["weather_label"] == "seco"
    assert r.json()["modelo"] is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && .venv/bin/python -m pytest -q tests/integracao/test_ingest_fixa.py`
Expected: FAIL (`tipo` desconhecido no cadastro; `modelo` ausente na resposta).

- [ ] **Step 3: Schemas** (`backend/app/schemas/device.py`)

```python
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class DeviceCreate(BaseModel):
    """Payload para registrar um dispositivo: Jetson ('movel') ou câmera parada ('fixa')."""

    name: str = Field(..., min_length=1, max_length=100, description='Ex: "carro-01" ou "fixa-sp_centro_geolan"')
    vehicle_plate: Optional[str] = Field(default=None, max_length=20)
    hw_model: Optional[str] = Field(default=None, max_length=50, description='Ex: "jetson_xavier"')
    metadata_: Optional[dict[str, Any]] = None
    tipo: Literal["movel", "fixa"] = "movel"
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    stream_url: Optional[str] = Field(default=None, max_length=500)
    descricao: Optional[str] = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _fixa_tem_posicao(self) -> "DeviceCreate":
        if self.tipo == "fixa" and (self.latitude is None or self.longitude is None):
            raise ValueError("câmera fixa exige latitude e longitude no cadastro")
        return self
```

Em `DeviceResponse` e `DevicePublico`, acrescentar:

```python
    tipo: str = "movel"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    stream_url: Optional[str] = None
    descricao: Optional[str] = None
```

Em `backend/app/schemas/capture.py`, no `CaptureResponse`:

```python
    modelo: Optional[str] = None
    modelo_versao: Optional[str] = None
```

- [ ] **Step 4: Serviço e rota de dispositivos**

`DeviceService.create_device` recebe e grava `tipo`, `latitude`, `longitude`, `stream_url`, `descricao` (parâmetros com default `"movel"`/`None`). Em `devices.py`, `register_device` repassa `body.tipo`, `body.latitude`, `body.longitude`, `body.stream_url`, `body.descricao` e devolve esses campos no `DeviceCreatedResponse(...)`.

- [ ] **Step 5: Regras no `media_service.py`**

Trocar o import `from app.services.inference_service import inference_service` por `from app.services.inference_service import roteador_inferencia`. No começo de `ingest`, depois do bloco de parse de `captured_at`, substituir a validação de obrigatórios e de lat/lon por:

```python
        fixa = device is not None and getattr(device, "tipo", "movel") == "fixa"
        required = {"captured_at", "source_type"} if fixa else {"captured_at", "latitude", "longitude", "source_type"}
        missing = required - meta.keys()
        if missing:
            raise HTTPException(status_code=400, detail=f"Campos obrigatórios ausentes no metadata: {sorted(missing)}")
```

(o parse de `captured_at` precisa vir depois desta checagem, como hoje). Em seguida:

```python
        if fixa:
            # Câmera fixa: posição é a do cadastro, não a do JSON, e o "seco" sem imagem
            # é decisão do gate da Jetson, que a câmera fixa não tem.
            if image is None:
                raise HTTPException(status_code=422, detail="Câmera fixa sempre envia a imagem; o modelo fixo decide se está seco.")
            latitude, longitude = device.latitude, device.longitude
            source_type = "camera_fixa"
        else:
            latitude, longitude = meta["latitude"], meta["longitude"]
            source_type = meta["source_type"]
            if (
                not isinstance(latitude, (int, float))
                or not isinstance(longitude, (int, float))
                or not (-90.0 <= latitude <= 90.0)
                or not (-180.0 <= longitude <= 180.0)
            ):
                raise HTTPException(status_code=400, detail="latitude deve estar entre -90 e 90 e longitude entre -180 e 180.")
```

Usar `source_type` nas duas construções de `Capture` (no lugar de `meta["source_type"]`). Trocar a chamada de inferência:

```python
        c = await roteador_inferencia.classificar(
            content, "fixa" if fixa else "movel", device.name if device else None, captured_at
        )
        weather_label, confidence = c.label, c.confianca
```

e acrescentar `modelo=c.modelo, modelo_versao=c.versao` no `Capture(...)` com imagem.

- [ ] **Step 6: Rodar e ver passar**

Run: `cd backend && .venv/bin/python -m pytest -q tests`
Expected: todos passam (unitários antigos, Task 3 e integração).

- [ ] **Step 7: Commit**

```bash
git add backend/app backend/tests/integracao/test_ingest_fixa.py
git commit -m "feat(backend): cadastro de câmera fixa e regras de ingestão por tipo"
```

---

### Task 5: Filtro `tipo` em capturas e heatmap

**Files:**
- Modify: `backend/app/services/capture_service.py`, `backend/app/api/v1/captures.py`, `backend/app/api/v1/stats.py`
- Test: `backend/tests/test_filtro_tipo.py` (SQL compilado, padrão do repo) e `backend/tests/integracao/test_filtro_tipo_integracao.py`

**Interfaces:**
- Produces: `_por_tipo(query, tipo: str) -> query` em `capture_service.py`; parâmetro `tipo: Optional[Literal["movel","fixa"]]` em `list_captures`, `get_h3_heatmap` e nas rotas `GET /captures/` e `GET /stats/geo`. Captura sem device (legado) conta como `movel`.

- [ ] **Step 1: Teste unitário que falha** (`backend/tests/test_filtro_tipo.py`)

```python
"""Filtro por tipo de dispositivo compila para o SQL esperado."""

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models.capture import Capture
from app.services.capture_service import _por_tipo


def _sql(q):
    return str(q.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_fixa_exige_device_fixo():
    sql = _sql(_por_tipo(select(Capture), "fixa"))
    assert "JOIN devices" in sql and "devices.tipo = 'fixa'" in sql


def test_movel_inclui_capturas_sem_device():
    sql = _sql(_por_tipo(select(Capture), "movel"))
    assert "LEFT OUTER JOIN devices" in sql
    assert "devices.tipo = 'movel'" in sql and "captures.device_id IS NULL" in sql
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_filtro_tipo.py`
Expected: `ImportError: cannot import name '_por_tipo'`.

- [ ] **Step 3: Implementar**

Em `capture_service.py`:

```python
from sqlalchemy import func, or_, select

from app.models.device import Device


def _por_tipo(query, tipo: str):
    """Só capturas de dispositivos do tipo pedido. Captura sem device é legado da Jetson: conta como 'movel'."""
    if tipo == "fixa":
        return query.join(Device, Capture.device_id == Device.id).where(Device.tipo == "fixa")
    return query.outerjoin(Device, Capture.device_id == Device.id).where(
        or_(Device.tipo == "movel", Capture.device_id.is_(None))
    )
```

Acrescentar `tipo: Optional[str] = None` em `list_captures` e `get_h3_heatmap` (`if tipo: query = _por_tipo(query, tipo)`), e nas rotas:

```python
    tipo: Optional[Literal["movel", "fixa"]] = Query(default=None, description="Só câmeras fixas ou só móveis"),
```

repassando para o serviço (por nome, para não depender da ordem posicional).

- [ ] **Step 4: Teste de integração** (`backend/tests/integracao/test_filtro_tipo_integracao.py`)

```python
"""GET /captures?tipo= separa câmera fixa de Jetson."""

import io
import json

from PIL import Image

from app.services import inference_service as inf
from app.services.inference_service import Classificacao


def _jpeg(cor):
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), cor).save(buf, "JPEG")
    return buf.getvalue()


async def test_filtro_separa_os_dominios(client, criar_device, monkeypatch):
    async def falso(*a, **k):
        return Classificacao("garoa", 0.9, "m", "ep1")

    monkeypatch.setattr(inf.roteador_inferencia, "classificar", falso)
    fixa, kf = await criar_device("fx", tipo="fixa", latitude=-23.0, longitude=-46.0)
    movel, km = await criar_device("mv")
    meta_f = {"metadata": json.dumps({"captured_at": "2026-10-08T15:00:00Z", "source_type": "x"})}
    meta_m = {"metadata": json.dumps({"captured_at": "2026-10-08T15:00:00Z", "source_type": "jetson", "latitude": -23.1, "longitude": -46.1})}
    await client.post("/api/v1/ingest", data=meta_f, files={"image": ("a.jpg", _jpeg((9, 9, 9)), "image/jpeg")}, headers={"Authorization": f"Bearer {kf}"})
    await client.post("/api/v1/ingest", data=meta_m, files={"image": ("b.jpg", _jpeg((8, 8, 8)), "image/jpeg")}, headers={"Authorization": f"Bearer {km}"})

    so_fixa = (await client.get("/api/v1/captures/", params={"tipo": "fixa", "limit": 200})).json()
    so_movel = (await client.get("/api/v1/captures/", params={"tipo": "movel", "limit": 200})).json()
    assert fixa["id"] in {c["device_id"] for c in so_fixa}
    assert movel["id"] not in {c["device_id"] for c in so_fixa}
    assert fixa["id"] not in {c["device_id"] for c in so_movel}
```

- [ ] **Step 5: Rodar e ver passar**

Run: `cd backend && .venv/bin/python -m pytest -q tests`
Expected: todos passam.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/capture_service.py backend/app/api/v1/captures.py backend/app/api/v1/stats.py backend/tests/test_filtro_tipo.py backend/tests/integracao/test_filtro_tipo_integracao.py
git commit -m "feat(backend): filtro tipo=fixa|movel em capturas e heatmap"
```

---

### Task 6: Endpoints das câmeras e imagem da captura

**Files:**
- Create: `backend/app/schemas/camera.py`, `backend/app/services/camera_service.py`, `backend/app/api/v1/cameras.py`
- Modify: `backend/app/api/router.py`, `backend/app/api/v1/captures.py`
- Test: `backend/tests/integracao/test_cameras.py`

**Interfaces:**
- Produces (JSON público, sem credencial):
  - `GET /api/v1/cameras/?excluir_demo=false` → `list[CameraResumo]`:
    `{id, name, descricao, latitude, longitude, stream_url, is_active, last_seen_at, ultima_captura: {id, captured_at, weather_label, confidence, modelo} | null, imagem_url: "/api/v1/captures/<id>/imagem" | null}`. Ordenado por `name`.
  - `GET /api/v1/cameras/{device_id}/serie?horas=6&excluir_demo=false` (`1 ≤ horas ≤ 48`) → `list[PontoSerie]` `{captured_at, weather_label, confidence}` em ordem crescente de tempo; 404 se o device não existe ou não é `fixa`.
  - `GET /api/v1/captures/{capture_id}/imagem` → o arquivo (`FileResponse`, `media_type` do MediaFile); 404 se não há MediaFile ou o arquivo sumiu do disco.
- O Plano D consome exatamente esses nomes de campo.

- [ ] **Step 1: Testes que falham** (`backend/tests/integracao/test_cameras.py`)

```python
"""Lista de câmeras fixas, série e imagem da captura."""

import io
import json
from pathlib import Path

from PIL import Image

from app.services import inference_service as inf
from app.services.inference_service import Classificacao


def _jpeg(cor):
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), cor).save(buf, "JPEG")
    return buf.getvalue()


async def _enviar(client, chave, quando, cor, demo=False):
    meta = {"captured_at": quando, "source_type": "x"}
    if demo:
        meta["metadata"] = {"demo": {"origem": "teste"}}
    return await client.post("/api/v1/ingest", data={"metadata": json.dumps(meta)},
                             files={"image": ("f.jpg", _jpeg(cor), "image/jpeg")},
                             headers={"Authorization": f"Bearer {chave}"})


async def test_lista_so_fixas_com_ultima_captura(client, criar_device, monkeypatch):
    async def falso(*a, **k):
        return Classificacao("forte", 0.7, "fixa_f1", "ep7")

    monkeypatch.setattr(inf.roteador_inferencia, "classificar", falso)
    cam, chave = await criar_device("fixa-lista", tipo="fixa", latitude=-24.0, longitude=-46.3, descricao="Santos")
    jet, _ = await criar_device("jetson-lista")
    await _enviar(client, chave, "2026-10-08T15:00:00Z", (1, 1, 1))
    r2 = await _enviar(client, chave, "2026-10-08T15:01:00Z", (2, 2, 2))

    cams = (await client.get("/api/v1/cameras/")).json()
    ids = {c["id"] for c in cams}
    assert cam["id"] in ids and jet["id"] not in ids
    c = next(x for x in cams if x["id"] == cam["id"])
    assert c["ultima_captura"]["id"] == r2.json()["id"]
    assert c["ultima_captura"]["weather_label"] == "forte"
    assert c["imagem_url"] == f"/api/v1/captures/{r2.json()['id']}/imagem"


async def test_camera_sem_captura_tem_campos_nulos(client, criar_device):
    cam, _ = await criar_device("fixa-vazia", tipo="fixa", latitude=-24.0, longitude=-46.3)
    c = next(x for x in (await client.get("/api/v1/cameras/")).json() if x["id"] == cam["id"])
    assert c["ultima_captura"] is None and c["imagem_url"] is None


async def test_excluir_demo_pula_capturas_de_demonstracao(client, criar_device, monkeypatch):
    async def falso(*a, **k):
        return Classificacao("garoa", 0.6, "m", "ep1")

    monkeypatch.setattr(inf.roteador_inferencia, "classificar", falso)
    cam, chave = await criar_device("fixa-demo", tipo="fixa", latitude=-24.0, longitude=-46.3)
    real = await _enviar(client, chave, "2026-10-08T15:00:00Z", (3, 3, 3))
    await _enviar(client, chave, "2026-10-08T15:05:00Z", (4, 4, 4), demo=True)
    c = next(x for x in (await client.get("/api/v1/cameras/", params={"excluir_demo": True})).json() if x["id"] == cam["id"])
    assert c["ultima_captura"]["id"] == real.json()["id"]


async def test_serie_em_ordem_crescente(client, criar_device, monkeypatch):
    async def falso(*a, **k):
        return Classificacao("garoa", 0.6, "m", "ep1")

    monkeypatch.setattr(inf.roteador_inferencia, "classificar", falso)
    cam, chave = await criar_device("fixa-serie", tipo="fixa", latitude=-24.0, longitude=-46.3)
    from datetime import datetime, timedelta, timezone

    agora = datetime.now(timezone.utc)
    for i, cor in enumerate([(5, 5, 5), (6, 6, 6)]):
        await _enviar(client, chave, (agora - timedelta(minutes=10 - i)).isoformat(), cor)
    serie = (await client.get(f"/api/v1/cameras/{cam['id']}/serie", params={"horas": 1})).json()
    tempos = [p["captured_at"] for p in serie]
    assert len(serie) == 2 and tempos == sorted(tempos)


async def test_serie_de_device_movel_e_404(client, criar_device):
    jet, _ = await criar_device("jetson-serie")
    assert (await client.get(f"/api/v1/cameras/{jet['id']}/serie")).status_code == 404


async def test_imagem_da_captura_e_404_se_sumiu_do_disco(client, criar_device, monkeypatch, db):
    async def falso(*a, **k):
        return Classificacao("garoa", 0.6, "m", "ep1")

    monkeypatch.setattr(inf.roteador_inferencia, "classificar", falso)
    _, chave = await criar_device("fixa-img", tipo="fixa", latitude=-24.0, longitude=-46.3)
    cap = (await _enviar(client, chave, "2026-10-08T15:00:00Z", (7, 7, 7))).json()
    ok = await client.get(f"/api/v1/captures/{cap['id']}/imagem")
    assert ok.status_code == 200 and ok.headers["content-type"].startswith("image/")
    det = (await client.get(f"/api/v1/captures/{cap['id']}")).json()
    Path(det["media_files"][0]["file_path"]).unlink()
    assert (await client.get(f"/api/v1/captures/{cap['id']}/imagem")).status_code == 404
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && .venv/bin/python -m pytest -q tests/integracao/test_cameras.py`
Expected: FAIL com 404 em `/api/v1/cameras/`.

- [ ] **Step 3: Schemas** (`backend/app/schemas/camera.py`)

```python
"""Visão pública das câmeras fixas para o dashboard."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class UltimaCaptura(BaseModel):
    id: int
    captured_at: datetime
    weather_label: Optional[str] = None  # None = não medido, nunca renderizar como seco
    confidence: Optional[float] = None
    modelo: Optional[str] = None


class CameraResumo(BaseModel):
    id: int
    name: str
    descricao: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    stream_url: Optional[str] = None
    is_active: bool
    last_seen_at: Optional[datetime] = None
    ultima_captura: Optional[UltimaCaptura] = None
    imagem_url: Optional[str] = None


class PontoSerie(BaseModel):
    captured_at: datetime
    weather_label: Optional[str] = None
    confidence: Optional[float] = None
```

- [ ] **Step 4: Serviço** (`backend/app/services/camera_service.py`)

```python
"""Consultas das câmeras fixas (tipo='fixa')."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capture import Capture
from app.models.device import Device
from app.models.media_file import MediaFile
from app.schemas.camera import CameraResumo, PontoSerie, UltimaCaptura
from app.services.capture_service import _sem_demo


class CameraService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def listar(self, excluir_demo: bool = False) -> list[CameraResumo]:
        devices = (await self.db.execute(select(Device).where(Device.tipo == "fixa").order_by(Device.name))).scalars().all()
        saida = []
        for d in devices:
            q = select(Capture).where(Capture.device_id == d.id).order_by(Capture.captured_at.desc()).limit(1)
            if excluir_demo:
                q = _sem_demo(q)
            cap = (await self.db.execute(q)).scalar_one_or_none()
            saida.append(CameraResumo(
                id=d.id, name=d.name, descricao=d.descricao, latitude=d.latitude, longitude=d.longitude,
                stream_url=d.stream_url, is_active=d.is_active, last_seen_at=d.last_seen_at,
                ultima_captura=UltimaCaptura.model_validate(cap, from_attributes=True) if cap else None,
                imagem_url=f"/api/v1/captures/{cap.id}/imagem" if cap else None,
            ))
        return saida

    async def serie(self, device_id: int, horas: int, excluir_demo: bool = False) -> Optional[list[PontoSerie]]:
        d = await self.db.get(Device, device_id)
        if d is None or d.tipo != "fixa":
            return None
        desde = datetime.now(timezone.utc) - timedelta(hours=horas)
        q = select(Capture).where(Capture.device_id == device_id, Capture.captured_at >= desde).order_by(Capture.captured_at)
        if excluir_demo:
            q = _sem_demo(q)
        caps = (await self.db.execute(q)).scalars().all()
        return [PontoSerie.model_validate(c, from_attributes=True) for c in caps]

    async def arquivo_da_captura(self, capture_id: int) -> Optional[MediaFile]:
        q = select(MediaFile).where(MediaFile.capture_id == capture_id).order_by(MediaFile.id).limit(1)
        return (await self.db.execute(q)).scalar_one_or_none()
```

Com 6 a 10 câmeras, uma consulta por câmera é aceitável; não otimizar antes de precisar.

- [ ] **Step 5: Rotas**

`backend/app/api/v1/cameras.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.camera import CameraResumo, PontoSerie
from app.services.camera_service import CameraService

router = APIRouter()


@router.get("/", response_model=list[CameraResumo])
async def listar_cameras(
    excluir_demo: bool = Query(default=False, description="Ignora capturas de demonstração na última captura"),
    db: AsyncSession = Depends(get_db),
):
    """Câmeras fixas com a última captura classificada (público, sem credencial)."""
    return await CameraService(db).listar(excluir_demo)


@router.get("/{device_id}/serie", response_model=list[PontoSerie])
async def serie_camera(
    device_id: int,
    horas: int = Query(default=6, ge=1, le=48),
    excluir_demo: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    """Classes previstas nas últimas `horas`, em ordem de tempo."""
    serie = await CameraService(db).serie(device_id, horas, excluir_demo)
    if serie is None:
        raise HTTPException(status_code=404, detail="Câmera fixa não encontrada.")
    return serie
```

Em `captures.py`, **antes** da rota `/{capture_id}`:

```python
from pathlib import Path

from fastapi.responses import FileResponse

from app.services.camera_service import CameraService


@router.get("/{capture_id}/imagem")
async def imagem_da_captura(capture_id: int, db: AsyncSession = Depends(get_db)):
    """Arquivo da imagem; 404 se não houver ou se o disco do servidor não o tiver mais."""
    mf = await CameraService(db).arquivo_da_captura(capture_id)
    if mf is None or not Path(mf.file_path).is_file():
        raise HTTPException(status_code=404, detail="Imagem indisponível.")
    return FileResponse(mf.file_path, media_type=mf.mime_type)
```

Em `router.py`: `from app.api.v1 import cameras, captures, devices, media, stats` e `router.include_router(cameras.router, prefix="/cameras", tags=["cameras — Dashboard"])`.

- [ ] **Step 6: Rodar e ver passar**

Run: `cd backend && .venv/bin/python -m pytest -q tests`
Expected: todos passam.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/camera.py backend/app/services/camera_service.py backend/app/api backend/tests/integracao/test_cameras.py
git commit -m "feat(backend): endpoints das câmeras fixas, série e imagem da captura"
```

---

### Task 7: Documentação da API e do deploy

**Files:**
- Modify: `backend/app/main.py` (texto de `description`)
- Modify: `backend/.env.example`
- Modify: `docs/COMO-CONTINUAR.md` (seção Backend)

**Interfaces:** nenhuma de código.

- [ ] **Step 1:** Em `main.py`, acrescentar ao `description` um parágrafo: "**Câmera fixa:** dispositivo cadastrado com `tipo='fixa'`, latitude e longitude. Sempre envia a imagem (sem imagem → 422). A posição vem do cadastro. A classe vem do modelo fixo de 4 classes, que pode devolver `seco`. Use `GET /api/v1/cameras/` e `?tipo=fixa|movel` em `/captures` e `/stats/geo`."
- [ ] **Step 2:** Em `.env.example`, acrescentar `ADMIN_KEY=`, `INFERENCE_MODEL_PATH=`, `INFERENCE_MODEL_FIXA_PATH=`, `REFERENCIAS_DIR=`, com uma linha de comentário cada.
- [ ] **Step 3:** Em `docs/COMO-CONTINUAR.md`, na seção Backend: como rodar os testes de integração (`docker run ... postgres:16` + `TEST_DATABASE_URL`) e o aviso de que o Railway precisa de um **volume** montado em `UPLOAD_DIR` para as miniaturas das câmeras sobreviverem a um deploy.
- [ ] **Step 4:** `cd backend && .venv/bin/python -m pytest -q tests` → tudo verde.
- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/.env.example docs/COMO-CONTINUAR.md
git commit -m "docs(backend): câmera fixa na descrição da API e no guia"
```

---

### Task 8 (opcional, P1): Leituras de pluviômetro para o "previsto × medido"

Só começar depois que as tasks 1 a 7 e o Plano D Task 2 estiverem prontos. Sem ela, o dashboard mostra "sem leitura de estação".

**Files:**
- Create: `backend/alembic/versions/0005_station_readings.py`, `backend/app/models/station_reading.py`, `backend/app/api/v1/estacoes.py`, `backend/app/services/estacao_service.py`
- Modify: `backend/app/schemas/camera.py` (`estacao: Optional[LeituraEstacao]` em `CameraResumo`), `backend/app/services/camera_service.py`, `backend/app/models/__init__.py`, `backend/app/api/router.py`
- Test: `backend/tests/test_estacao_service.py`, `backend/tests/integracao/test_estacoes.py`

**Interfaces:**
- `POST /api/v1/estacoes/leituras` (admin): corpo `list[{estacao_id, nome, lat, lon, ts_utc, acumulado_mm, janela_min}]`; upsert por `(estacao_id, ts_utc)`; devolve `{"inseridas": n}`.
- `LeituraEstacao`: `{nome, distancia_km, mm_h, ts_utc}`.
- `mm_h_recente(leituras, agora, janela_min=30) -> Optional[float]` (pura): soma dos `acumulado_mm` com `ts_utc` em `(agora − 30 min, agora]` dividida por `(n × janela_min / 60)`; `None` sem leituras.
- `CameraResumo.estacao`: estação com leitura mais próxima a ≤ 5 km (haversine), ou `null`.

- [ ] **Step 1: Teste unitário que falha** (`backend/tests/test_estacao_service.py`)

```python
from datetime import datetime, timedelta, timezone

from app.services.estacao_service import mm_h_recente

AGORA = datetime(2026, 10, 8, 18, 0, tzinfo=timezone.utc)


def L(min_atras, mm):
    return {"ts_utc": AGORA - timedelta(minutes=min_atras), "acumulado_mm": mm, "janela_min": 10}


def test_tres_leituras_de_10_min():
    assert mm_h_recente([L(0, 1.0), L(10, 0.5), L(20, 0.5)], AGORA) == 4.0  # 2 mm em 30 min


def test_ignora_leituras_velhas():
    assert mm_h_recente([L(45, 9.0), L(5, 0.2)], AGORA) == 1.2


def test_sem_leitura_e_none():
    assert mm_h_recente([], AGORA) is None
```

- [ ] **Step 2:** rodar e ver falhar (`ModuleNotFoundError`).
- [ ] **Step 3:** implementar `estacao_service.py` com `mm_h_recente` e `haversine_km`; migração `0005` criando `station_readings(id PK, estacao_id String(30), nome String(100), lat Float, lon Float, ts_utc DateTime(tz), acumulado_mm Float, janela_min Integer, UNIQUE(estacao_id, ts_utc), INDEX(ts_utc))`; modelo; rota admin com `insert ... on_conflict_do_nothing` (`sqlalchemy.dialects.postgresql.insert`).
- [ ] **Step 4:** teste de integração: postar 3 leituras de uma estação a 1 km de uma câmera com `ts_utc` nos últimos 30 min; `GET /cameras/` mostra `estacao.mm_h` correto e `distancia_km < 1.5`.
- [ ] **Step 5:** `pytest -q tests` verde; commit `feat(backend): leituras de pluviômetro e previsto x medido nas câmeras`.
