# backend/ — API do CityRain

API em FastAPI que recebe as fotos do carro (Jetson) e das câmeras fixas, classifica a intensidade da chuva com modelos ONNX, grava no PostgreSQL com o índice espacial H3 e serve o painel web.

Produção: https://api-production-046f.up.railway.app (documentação interativa em [`/docs`](https://api-production-046f.up.railway.app/docs)).

## Stack

| Camada | Tecnologia |
|---|---|
| HTTP | FastAPI + Uvicorn (async) |
| Banco | PostgreSQL 16, SQLAlchemy 2 async, Alembic |
| Espacial | H3 (resolução 8, hexágono de ~460 m) |
| Inferência | onnxruntime em CPU; pré-processamento lido do próprio `.onnx` |
| Deploy | Railway (Nixpacks, `railway.toml`) |

## Estrutura

```
backend/
├── app/
│   ├── main.py              # app, CORS, lifespan (checagem do banco e retenção periódica), /health
│   ├── api/v1/              # rotas: media (ingest), captures, cameras, veiculos, stats, devices
│   ├── core/                # config (variáveis de ambiente), banco, autenticação
│   ├── models/              # SQLAlchemy: Capture, Device, MediaFile, IngestionLog
│   ├── schemas/             # Pydantic (requisição e resposta)
│   ├── services/            # regra de negócio: ingestão, inferência, câmeras, veículos, retenção, H3
│   └── inference/modelos/   # intensidade.onnx (carro) e intensidade_fixa.onnx (câmera fixa)
├── alembic/                 # migrações (0001 → 0004)
└── tests/                   # unitários + integracao/ (PostgreSQL real)
```

## Rotas

| Método e rota | Acesso | Para quê |
|---|---|---|
| `POST /api/v1/ingest` | token do dispositivo | foto (JPEG/PNG) + metadata JSON; classifica e grava |
| `GET /api/v1/captures/` | público | capturas com filtros (classe, período, dispositivo, `tipo=movel\|fixa`, `excluir_demo`) |
| `GET /api/v1/captures/{id}` | público | detalhe da captura (sem caminho de arquivo nem erro interno) |
| `GET /api/v1/captures/{id}/imagem` | público | foto **só de câmera fixa**; foto do carro nunca é servida (LGPD) |
| `GET /api/v1/cameras/` · `/{id}/serie` | público | câmeras fixas com a última captura; série temporal |
| `GET /api/v1/veiculos/` | público | veículos ativos com a última captura (sem placa, sem foto) |
| `GET /api/v1/stats/geo` | público | agregação por célula H3 |
| `GET /api/v1/devices/publico` | público | dispositivos ativos, sem placa nem credencial |
| `POST/GET/DELETE /api/v1/devices/` | chave de admin | cadastrar, listar e desativar dispositivos |
| `GET /health` · `/health/db` | público | API no ar; banco acessível |

## Como a ingestão decide

- **Carro sem imagem:** o gate da Jetson já decidiu que está seco; grava `seco` com confiança nula.
- **Carro com imagem:** modelo do carro (`intensidade.onnx`, 3 classes: garoa, moderado, forte).
- **Câmera fixa:** sempre com imagem; posição vem do cadastro; modelo de 4 classes (`intensidade_fixa.onnx`).
- **Sem modelo carregado:** a intensidade fica **nula** ("não medida"), nunca vira "seco".
- **Reenvio:** o sha256 da imagem identifica retry da Jetson; a resposta é 200 com a captura já gravada.
- **Demonstração:** `metadata.demo` marca replays; o histórico pode excluí-los (`excluir_demo=true`).

## Segurança

- Tokens de dispositivo gerados com `secrets.token_urlsafe(32)`; o banco guarda só o SHA-256. Chaves comparadas em tempo constante.
- Upload validado pelo **conteúdo** (bytes iniciais de JPEG ou PNG), com teto de tamanho (`MAX_UPLOAD_SIZE_MB`) e metadata limitado a 16 KB. Nome e extensão do arquivo salvo nunca vêm do cliente.
- Rotas públicas não expõem caminho de arquivo, mensagem de erro interna, placa ou foto do carro.
- CORS restrito às origens configuradas, sem credenciais de navegador (a autenticação é por Bearer).
- Imagens de câmera fixa são apagadas do disco depois de `RETENCAO_IMAGEM_FIXA_MIN` minutos; as linhas da captura ficam.

## Variáveis de ambiente

Copie `.env.example` para `.env`. As principais:

| Variável | Obrigatória | Descrição |
|---|---|---|
| `DATABASE_URL` | sim | `postgresql+asyncpg://...` (o `postgresql://` do Railway é convertido sozinho) |
| `ADMIN_KEY` | para cadastrar dispositivos | vazia = rotas de admin respondem 401 |
| `API_KEY` | não | chave legada única (prefira um token por dispositivo) |
| `CORS_ORIGINS` | em produção | lista JSON ou separada por vírgula |
| `INFERENCE_MODEL_PATH`, `INFERENCE_MODEL_FIXA_PATH` | não | caminhos dos modelos; vazio = os de `app/inference/modelos/` |
| `UPLOAD_DIR`, `MAX_UPLOAD_SIZE_MB`, `RETENCAO_INTERVALO_S` | não | armazenamento, teto de upload, varredura de retenção |

## Rodar localmente

Use **Python 3.11**: o `sqlalchemy==2.0.37` fixado não importa em 3.14 (`TypeError: descriptor '__getitem__' requires a 'typing.Union' object`). O `.python-version` fixa a mesma versão no Railway.

```bash
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env            # DATABASE_URL e ADMIN_KEY
alembic upgrade head
uvicorn app.main:app --reload   # http://localhost:8000/docs
```

Banco de teste descartável com Docker:

```bash
docker run -d --rm --name cityrain-pg -e POSTGRES_USER=cr -e POSTGRES_PASSWORD=cr -e POSTGRES_DB=cityrain_test -p 55432:5432 postgres:16-alpine
TEST_DATABASE_URL=postgresql+asyncpg://cr:cr@localhost:55432/cityrain_test pytest   # sem a variável, os testes de integração são pulados
```

## Trocar um modelo

O backend lê do próprio `.onnx` as classes, o tamanho da entrada e a normalização: trocar o modelo é trocar o arquivo em `app/inference/modelos/`. Antes, confira com:

```bash
backend/.venv/bin/python ml/scripts/avaliacao/checar_modelo_fixa.py novo.onnx   # câmera fixa
```

Passo a passo completo em [`docs/GUIA-TREINO-EQUIPE.md`](../docs/GUIA-TREINO-EQUIPE.md) §6.
