# Como continuar o CityRain

> Estado em 07/10/2026. Leia isto antes do resto: o `README.md` e partes do `CLAUDE.md` ainda
> descrevem o projeto como estava no pré-projeto (framework e arquitetura "abertos"). Isso já foi
> decidido — ver abaixo.

## 1. Onde o projeto está

- **Sistema em produção, ponta a ponta:** Jetson (gate chuva/seco) → `POST /api/v1/ingest`
  (Railway) → modelo de intensidade ONNX no backend → PostgreSQL → dashboard
  (https://cityrain.vercel.app).
- **Modelo de intensidade em produção:** v3, MobileNetV3-Large (PyTorch → ONNX), 288×384,
  classes garoa | moderada | forte (`seco` é decidido pelo gate na Jetson). Arquivo:
  `backend/app/inference/modelos/intensidade.onnx`.
- **Todos os experimentos e números:** `docs/resultados-experimentos.md` (rascunho do capítulo
  de resultados — uma tabela com v1 a v5, baseline físico, híbrido, IC 95%, benchmark da Jetson).
- **Estratégia do dataset:** `docs/specs/` e `docs/plano-dataset.md`. Resumo: real (seco/garoa,
  rotulado por pluviômetro CEMADEN) + sintético calibrado (moderada/forte, só no treino) + irCNN
  (dataset público com pluviômetro, validação cruzada por evento).
- **Demonstração para a banca:** `docs/roteiro-demo-defesa.md`.
- **Inventário de todas as imagens:** `docs/acervo-dados.md`.

## 2. O que NÃO está no Git (e por quê)

Imagens e modelos treinados somam ~32 GB — não cabem no GitHub (limite de 100 MB por arquivo e
repositórios grandes ficam inutilizáveis). Ficam fora do Git por `.gitignore` e são distribuídos
em zips:

| Zip | Conteúdo | Descompactar em |
|---|---|---|
| `1_dados_proprios.zip` | nossas coletas (`raw/imt_coleta`), câmeras fixas, leituras das estações, `processed/`, `synthetic/`, `splits/`, `review/` | raiz do repo (`CityRain/`) |
| `2_modelos_treinados.zip` | `ml/runs/` — checkpoints (`melhor.pt`), métricas e predições de todos os runs | raiz do repo |
| `3_datasets_publicos.zip` | `ml/data/raw/public_datasets/` — irCNN, YouTube, Zenodo (24 GB) | raiz do repo |
| `4_coleta_maio_bruta.zip` | frames de maio/2026 com horário corrompido (não usados no treino) | pasta acima do repo (`code/`) |

Os zips guardam os caminhos relativos: rodar `unzip <arquivo>.zip` **dentro de `CityRain/`**
(exceto o 4) já coloca tudo no lugar que o código espera. Os manifests de rótulos
(`ml/data/manifests/`) e os configs (`ml/configs/`) **estão** no Git.

## 3. Rodar cada parte

### ML (treino e avaliação)

```bash
python3.11 -m venv ml/.venv            # 3.11+; o treino foi feito em 3.14
ml/.venv/bin/pip install -r ml/requirements-ci.txt torch torchvision onnx onnxruntime
ml/.venv/bin/python -m pytest -q ml/tests

# validação cruzada por evento do irCNN (4 folds, ~20 min cada em Mac M-series)
ml/.venv/bin/python ml/scripts/treino/treinar_intensidade.py ml/configs/treino_intensidade_cv_v3_mnv3.yaml --cv
# um fold por vez (mais seguro: use caffeinate -i no Mac para ele não dormir)
ml/.venv/bin/python ml/scripts/treino/treinar_intensidade.py <config> --fold 0
# modelo de produção (todos os eventos no treino) e exportação para o backend
ml/.venv/bin/python ml/scripts/treino/treinar_intensidade.py ml/configs/treino_intensidade_final_v3_mnv3.yaml --fold final
ml/.venv/bin/python ml/scripts/treino/exportar_onnx.py ml/runs/<run>/melhor.pt
```

Avaliações extras (Grad-CAM, IC por bootstrap, híbrido, baseline físico) estão em
`ml/scripts/avaliacao/`; os resumos versionados saem em `ml/resultados/`.

### Backend

```bash
cd backend && python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # preencher DATABASE_URL etc.
.venv/bin/python -m pytest -q tests
```

Use Python 3.11 (SQLAlchemy 2.0.37 quebra no 3.14). Deploy no Railway a partir da `main`.

**Testes de integração com PostgreSQL local:**

```bash
# Subir container PostgreSQL para testes
docker run -d --name cityrain-pg-teste \
  -e POSTGRES_USER=cityrain \
  -e POSTGRES_PASSWORD=cityrain \
  -e POSTGRES_DB=cityrain_teste \
  -p 5433:5432 postgres:16

# Executar testes apontando para o banco de testes
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://cityrain:cityrain@localhost:5433/cityrain_teste .venv/bin/python -m pytest -q tests
```

**Aviso sobre deploy no Railway:**

O diretório `UPLOAD_DIR` (padrão `storage/`) armazena miniaturas de câmeras e outros artefatos. 
Em um container ephemeral (Railway), esses arquivos são perdidos a cada deploy. 
**Montar um volume persistente em `UPLOAD_DIR`** para que as imagens sobrevivam entre deploys. 
Sem o volume, o dashboard mostrará quebras de imagem após redeploy.

### Frontend

```bash
cd frontend && npm ci && cp .env.example .env.local   # VITE_API_URL
npm run dev     # http://localhost:5173
```

Deploy no Vercel: `npx vercel deploy --prod --yes` dentro de `frontend/`.

### Jetson

`ml/scripts/captura/implantar_jetson.sh` (implantar e `verificar`). O código embarcado é
compatível com Python 3.6.

## 4. Pendências até 20/10

1. **Moderada e forte reais no para-brisa** — saídas em dia de chuva ou piloto de chuva simulada
   (`docs/protocolo-piloto-chuva-simulada.md`).
2. **Sessões secas de dia e de noite** — para refazer o gate da Jetson (hoje deixa passar só
   10–36% da chuva real).
3. **Decidir o híbrido** (CNN + atributos físicos) para produção — `ml/scripts/avaliacao/ensemble_hibrido.py`.
4. **Câmera conectada na Jetson** em fluxo contínuo.
5. **Escrever o capítulo de resultados** a partir de `docs/resultados-experimentos.md`.

Regras que valem para qualquer experimento novo: split **por evento**, nunca por frame; sintético
**nunca** entra em teste; rótulo vem de pluviômetro, não do olho.
