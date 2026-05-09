# backend/ — API HTTP

API que recebe inferências do modelo, ingere dados de pluviômetros públicos, agrega espacialmente em células H3 e expõe os dados para o `frontend/`.

## Stack (definido)

- **FastAPI** + **Uvicorn** (Python async)
- **PostgreSQL** (persistência de inferências, séries temporais e estações)
- **H3** (Uber) — agregação espacial em células hexagonais
- **Alembic** — migrations
- **Pydantic** — schemas de request/response
- **httpx** — cliente HTTP para CGE-SP / INMET / CEMADEN

## Estrutura

```
backend/
├── app/
│   ├── api/         # Routers HTTP (endpoints)
│   ├── core/        # Config, settings, logging
│   ├── db/          # Models SQLAlchemy + sessão
│   ├── ingestion/   # Clients de APIs públicas (CGE-SP, INMET, CEMADEN) + jobs de ingestão
│   ├── inference/   # Carrega modelo exportado (ONNX) e roda inferência sobre frames recebidos
│   ├── h3/          # Conversão lat/lng → célula H3, agregação por célula
│   └── schemas/     # Pydantic
├── migrations/      # Alembic
└── tests/
```

## Fluxos principais

1. **Ingestão de ground truth (offline / cron):** lê APIs públicas → grava em Postgres com timestamp e geolocalização da estação.
2. **Inferência online:** câmera envia frame → modelo classifica → resultado vai para Postgres com `h3_index` (célula) e timestamp.
3. **Consulta do frontend:** dashboard pede o estado atual por célula H3 → backend retorna a classe agregada (mais recente / moda na janela) por célula.

## Como rodar (placeholder)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env  # ajustar DATABASE_URL
alembic upgrade head
uvicorn app.main:app --reload
```
