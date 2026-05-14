# CLAUDE.md — CityRain

## Sobre o Projeto

CityRain é um sistema embarcado de monitoramento climático urbano por visão computacional de borda. O sistema utiliza redes neurais convolucionais otimizadas para **classificar a intensidade da precipitação pluviométrica em quatro categorias** (`seco`, `garoa`, `moderada`, `forte`) a partir de imagens capturadas por câmeras, com latência de inferência em tempo real.

A aplicação primária é um **dashboard web (React) para monitoramento pluviométrico urbano em tempo real**, com agregação espacial por células hexagonais H3. O **ground truth** para treinamento e validação vem de **pluviômetros públicos urbanos** (CGE-SP, INMET, CEMADEN) — não há pluviômetro embarcado na coleta da equipe.

> **Importante — papel das estações públicas:** as estações são usadas **apenas em duas etapas**: (1) **treinamento** — para gerar os labels do dataset associando frames de câmera à intensidade medida pela estação mais próxima na mesma janela de tempo; (2) **validação/avaliação** — para medir acurácia comparando a predição do modelo contra a leitura da estação. **Em inferência (produção), o modelo recebe apenas a imagem da câmera** e produz a classe (`seco`, `garoa`, `moderada`, `forte`) a partir dos pesos aprendidos. Não há consulta a estação meteorológica em tempo de predição.

> **Escopo atual:** classificação em 4 níveis. **Escopo futuro (condicionado a resultados):** estimativa quantitativa de intensidade em mm/h. A migração para regressão depende da viabilidade demonstrada na fase de classificação e da qualidade do alinhamento espaço-temporal câmera ↔ estação pluviométrica.

Este é um TCC do curso de Ciência da Computação do Centro Universitário do Instituto Mauá de Tecnologia (IMT).

**Título formal:** CityRain: Sistema Embarcado de Monitoramento Climático Urbano por Visão Computacional

## Equipe

- **Rodrigo Monteiro Toffoli Teixeira** — 23.00068-6
- **Guilherme Mattioli** — 20.00599-7
- **Gabriel Moreno** — 23.01528-4
- **Paulo Vespero** — 23.00607-2
- **Orientador:** Prof. Gabriel de Souza Lima

## Princípios de Desenvolvimento

> **IMPORTANTE — Ler antes de sugerir qualquer solução:**

1. **Não prender framework de ML.** O projeto está em fase de experimentação. Não assumir PyTorch, TensorFlow, YOLO, ou qualquer framework específico como escolha definitiva. Todas as sugestões devem ser agnósticas ou apresentar alternativas comparativas. Queremos testar o máximo possível antes de decidir.

2. **Não prender arquitetura de modelo.** Não assumir ResNet, MobileNet, YOLO, ou qualquer arquitetura como definitiva. O trabalho envolve investigar e comparar múltiplas abordagens (classificadores, detectores de estágio único, modelos de regressão, abordagens baseadas em física). Sempre apresentar como experimento, não como decisão.

3. **Aplicação primária definida (dashboard urbano), saída do modelo não.** A aplicação alvo é um dashboard web em tempo real alimentado por câmeras + pluviômetros públicos. A *saída do modelo de percepção*, no entanto, ainda é objeto de experimentação: classificação em 4 níveis no escopo atual, regressão em mm/h como possibilidade futura. Não fechar abordagens.

4. **Experimentação acima de tudo.** Quanto mais testes, comparações e benchmarks, melhor. Preferir código que facilite experimentação rápida (configs, abstrações, logging) sobre código otimizado prematuramente.

5. **Simplicidade e reprodutibilidade.** É um TCC de graduação. Soluções devem ser implementáveis pela equipe no prazo (março–novembro 2026). Evitar over-engineering.

6. **Classificação primeiro, regressão depois.** O caminho até mm/h passa obrigatoriamente por uma fase de classificação 4-classes bem caracterizada. Só migrar para regressão após (i) validar acurácia da classificação e (ii) confirmar que o alinhamento câmera ↔ estação pluviométrica pública é preciso o suficiente para servir como ground truth contínuo.

## Duas Frentes de Abordagem a Investigar

O projeto tem dois caminhos possíveis (não mutuamente exclusivos) para estimar intensidade de chuva:

### Frente A — Detecção de gotas + modelagem física
- Detectar gotas de chuva e artefatos ópticos na imagem (rain streaks, distorções no para-brisa)
- Usar modelagem física (transmissão atmosférica, coeficiente de extinção óptica, equações de Koschmieder) para converter a degradação visual em intensidade (mm/h)
- Referência: Kanazawa & Uchida (HESS, 2025), Roser et al. (2009)

### Frente B — Regressão direta imagem → intensidade via CNN
- Treinar uma CNN para mapear diretamente a imagem (ou sequência de frames) para um valor contínuo de intensidade (mm/h)
- Sem detecção explícita de gotas — o modelo aprende features relevantes end-to-end
- Referência: irCNN (Yin et al., 2023), DSC-GRU (2025), CNN-LSTM Bayesiano (Zheng et al., 2024)

### Abordagem híbrida (possível)
- Pré-processar a imagem para extrair informação de gotas/rain streaks e alimentar o modelo como features adicionais
- Referência: Zheng et al. (Water Resources Research, 2023)

## Arquiteturas Candidatas (a investigar, não definidas)

| Categoria | Candidatos | Propósito |
|-----------|-----------|-----------|
| Detectores de estágio único | YOLOv8, YOLOv10, YOLOv11, RT-DETR | Detecção de gotas em tempo real |
| CNNs para regressão | ResNet18/34, MobileNetV2/V3, EfficientNet-B0/B1 | Regressão direta imagem → mm/h |
| Modelos temporais | CNN + LSTM, CNN + GRU, 3D-CNN | Explorar informação temporal de sequências de frames |
| Modelos leves para edge | MobileNetV3-Small, ShuffleNet, SqueezeNet | Otimização para hardware de borda |
| Abordagens físicas | Dark Channel Prior + equações de extinção | Baseline analítico sem ML |

**Todas são candidatas. Nenhuma é a escolha final.**

## Pipeline do Sistema (arquitetura macro)

```
[Câmera] → [Pré-processamento] → [Modelo de Percepção] → [Classificação 4 níveis] → [Backend] ⇄ [Frontend React]
                                        ↑                          ↑                  ↑              ↑
                                   A investigar            Saída atual:        FastAPI/Uvicorn   Dashboard com
                                   (ver candidatos)        seco, garoa,        PostgreSQL        agregação H3
                                                           moderada, forte     (persistência)    em tempo real
                                                           (regressão = futuro) H3 (agregação)

  Jetson → Backend: protocolo em análise (HTTP vs MQTT — ver "Decisões abertas").
  Frontend ⇄ Backend: HTTP (REST). Backend → APIs públicas: HTTP.
  Inferência: modelo recebe SÓ a imagem. Estações públicas entram apenas no fluxo offline:
  [Estações CGE-SP/INMET/CEMADEN] → labels do dataset (treino) + comparação com predição (avaliação)
```

### Stack de Backend

**Definido:**
- **Framework** — FastAPI servido por **Uvicorn** (Python async)
- **Banco de dados** — **PostgreSQL** para persistência de inferências, estações públicas e séries temporais
- **Agregação espacial** — **H3** (Uber) para indexar células hexagonais sobre o mapa urbano
- **Ingestão de ground truth** — requisições HTTP às APIs públicas (CGE-SP, INMET, CEMADEN)
- **Frontend ⇄ Backend** — React consumindo API REST/HTTP do backend

**Em análise:**
- **Protocolo Jetson → Backend** — escolha entre HTTP e MQTT. HTTP é mais simples e alinhado ao stack já adotado; MQTT é mais robusto a conectividade intermitente, cenário típico da coleta veicular. Decisão pendente.

## Datasets Identificados

### Com label de intensidade real (mm/h) — PRIORIDADE MÁXIMA
| Dataset | Descrição | Link |
|---------|-----------|------|
| irCNN (Figshare) | 6 vídeos de chuva + dados de pluviômetro, Hangzhou | https://doi.org/10.6084/m9.figshare.22122500.v1 |
| AAU VIRADA (Zenodo) | 215h de vídeo de vigilância + precipitação, Aalborg | https://zenodo.org/records/4715681 |
| Rain_CCTV (Lee et al.) | Câmera IR + disdrômetro, condições noturnas | https://github.com/jinwook213/Rain_CCTV |

### Datasets de rain streaks / deraining (pré-treino, augmentação)
| Dataset | Descrição | Link |
|---------|-----------|------|
| DID-MDN Rain1200 | Sintético, 3 níveis de densidade (light/medium/heavy) | https://github.com/hezhangsprinter/DID-MDN |
| LHP-Rain (ICCV 2023) | 1M frames reais 1920x1080 em 3000 sequências | https://github.com/yunguo224/LHP-Rain |
| SPA-Data (CVPR 2019) | ~29.5K pares rain/clean reais | https://github.com/stevewongv/SPANet |
| Rain100H / Rain100L | Benchmarks clássicos de deraining | https://github.com/hongwang01/Video-and-Single-Image-Deraining |

### Contexto automotivo / driving
| Dataset | Descrição | Link |
|---------|-----------|------|
| RID — Rain in Driving | Chuva em cenário de direção + labels de objetos | https://github.com/lsy17096535/Single-Image-Deraining |
| RainCityscapes | Chuva sintética sobre Cityscapes urbano | (via repo Video-and-Single-Image-Deraining) |
| RaindropsOnWindshield | Gotas de chuva em para-brisas (Evocargo) | https://github.com/Evocargo/RaindropsOnWindshield |
| Adver-City | Multi-modal, condições climáticas adversas | arXiv:2410.06380 |

### Para transfer learning
| Dataset | Descrição | Link |
|---------|-----------|------|
| ImageNet | 1.28M imagens, 1000 classes — pré-treino de CNNs | https://www.image-net.org/ |
| COCO | Detecção de objetos — se usar detectores tipo YOLO | https://cocodataset.org/ |

### Agregadores (hubs com todos os datasets de chuva)
- https://github.com/guyii54/Real-Rainy-Image-Datasets (~34.9K imagens + 68 vídeos)
- https://github.com/nnUyi/DerainZoo (master list de datasets e métodos)
- https://github.com/hongwang01/Video-and-Single-Image-Deraining (survey completa)

## Coleta de Dados Próprios

A coleta de dados próprios é **veicular**, com câmera instalada em um veículo percorrendo a Região Metropolitana de São Paulo e o ABC Paulista, e não em ponto fixo no campus. Setup:
- **Plataforma embarcada**: NVIDIA Jetson Nano com script de captura rodando no boot (`ml/scripts/captura/`) e botão físico de desligamento seguro.
- **Câmera**: USB ou IP (720p+) montada no veículo.
- **GPS** (em aquisição): associa cada frame à estação pública mais próxima naquele instante. Esse é o pivô do pipeline de rotulação, sem GPS funcional o alinhamento câmera ↔ estação fica inviável em deslocamento.
- **Ground truth para rotulação e validação via pluviômetros públicos urbanos** (CGE-SP, INMET, CEMADEN) — sem pluviômetro embarcado da equipe. A sincronização temporal é feita via NTP.
- Anotar condições: dia/noite, vento, tipo de chuva, ângulo da câmera.
- Estação chuvosa em SP: outubro–março (considerar no cronograma).
- Para a fase atual (classificação 4-classes), os labels `seco`, `garoa`, `moderada`, `forte` **do dataset** são derivados da leitura mm/h da estação pública mais próxima naquele instante de coleta, com janelas de tempo definidas. Esses labels existem só para treinar e avaliar — **o modelo final não consulta nenhuma estação em inferência**, ele decide a classe puramente a partir da imagem.

> **Implicação técnica da coleta veicular:** o fundo é dinâmico (carros, faixas, iluminação variável). Isso reforça a relevância dos achados de Qin et al. (2025, ResNet-LSTM para fundos dinâmicos) e justifica incluir modelos temporais (CNN+LSTM/GRU) entre os experimentos.

## Métricas de Avaliação

### Performance do modelo — fase atual (classificação 4-classes)
- **Acurácia** geral e por classe
- **Matriz de confusão** entre `seco`, `garoa`, `moderada`, `forte`
- **F1-score** macro e por classe (importante por desbalanceamento típico — classe `seco` tende a dominar)
- **Precisão e Recall** por classe (recall em `forte` é crítico para alertas)

### Performance do modelo — fase futura (regressão mm/h, condicional)
- **MAE** — Mean Absolute Error (mm/h)
- **MAPE** — Mean Absolute Percentage Error (%)
- **R²** — Coeficiente de determinação
- **NSE** — Nash-Sutcliffe Efficiency
- **KGE** — Kling-Gupta Efficiency

### Performance de edge (viabilidade embarcada)
- Latência por frame (ms)
- Throughput (FPS)
- Uso de memória (MB)
- Consumo energético (W)
- Degradação de acurácia pós-quantização

### Referência da literatura (alvos)
- irCNN: MAPE 13.5%–21.9%, R² 0.92
- DSC-GRU: R² 0.89–0.93
- irCNN inferência: ~100 imagens em 1-2 segundos

## Papers de Referência

### Detecção e quantificação de chuva por imagem
1. Yin et al. (2023) — "Estimating Rainfall Intensity Using an Image-Based Deep Learning Model" — Engineering, Vol. 21
2. Zheng et al. (2023) — "Toward Improved Real-Time Rainfall Intensity Estimation Using Video Surveillance Cameras" — Water Resources Research
3. Zheng et al. (2024) — CNN-LSTM Bayesiano para estimativa de intensidade com incerteza — Journal of Hydrology
4. Kanazawa & Uchida (2025) — "Rainfall intensity estimations based on degradation characteristics of images" — HESS
5. DSC-GRU (2025) — "Toward accurate and scalable rainfall estimation using surveillance camera data" — Env. Sci. and Ecotechnology
6. ResNet-LSTM (2025) — "Real-time rainfall estimation using deep learning" — Science of the Total Environment

### Detecção de gotas e contexto automotivo
7. Roser et al. (2009) — Raindrop detection on car windshields using geometric-photometric models
8. Guo & Breckon (2018) — Real-time rain drop detection with CNN + superpixels, precisão 0.95
9. He et al. (2009) — Single Image Haze Removal Using Dark Channel Prior
10. Wang et al. (2026) — YOLOv11-TWCS: detecção em condições adversas, >100 FPS

### Agregação espacial e ingestão de dados públicos
11. Brodeur et al. (2018) — "H3: Uber's Hexagonal Hierarchical Spatial Index"
12. APIs públicas: CGE-SP (https://www.cgesp.org/), INMET (https://portal.inmet.gov.br/), CEMADEN (https://www.gov.br/cemaden/)

## Cronograma (do pré-projeto aprovado)

| Atividade | Mar | Abr | Mai | Jun | Jul | Ago | Set | Out | Nov |
|-----------|-----|-----|-----|-----|-----|-----|-----|-----|-----|
| Levantamento bibliográfico | X | X | X | | | | | | |
| Levantamento de requisitos | X | X | | | | | | | |
| Prototipação inicial | | X | X | X | | | | | |
| Desenvolvimento do sistema | | | X | X | X | X | | | |
| Calibração e ajustes | | | | X | X | X | | | |
| Testes e validação | | | | | | X | X | | |
| Redação do TCC | | | | | X | X | X | X | |
| Revisão e apresentação | | | | | | | | X | X |

## Objetivos Específicos (do pré-projeto)

a) Investigar e comparar técnicas de pré-processamento para isolamento de regiões de interesse com gotas e distorções ópticas
b) Treinar e avaliar modelos CNN de referência como prova de conceito para classificação em 4 níveis (`seco`, `garoa`, `moderada`, `forte`), estabelecendo baselines de precisão e latência
c) Implementar e otimizar detectores de estágio único para detecção contínua em tempo real
d) Investigar viabilidade futura de estimativa quantitativa em mm/h (regressão), condicionada aos resultados da classificação e ao alinhamento câmera ↔ estação pública
e) Implantar modelo otimizado em hardware de borda com quantização e fusão de camadas
f) Construir backend de ingestão e agregação espacial (FastAPI + Uvicorn + PostgreSQL + H3) integrando inferências da câmera embarcada e ground truth de pluviômetros públicos (CGE-SP, INMET, CEMADEN) via HTTP/MQTT
g) Desenvolver painel de controle React para visualização em tempo real (mapa com células H3 coloridas pela classe de chuva e séries temporais)
h) Avaliar viabilidade da solução vs. métodos tradicionais (precisão, latência, custo)

## Estrutura do Repositório

O repositório é dividido em **três subprojetos top-level independentes**, cada um com seu próprio toolchain. Isso permite que cada pessoa do time trabalhe isolada (Python ML, Python backend, React/TS frontend) sem conflitos de dependências, e que cada parte possa ser containerizada separadamente no futuro.

```
cityrain/
├── CLAUDE.md
├── README.md
├── .gitignore
├── docs/                          # TCC (ABNT), referências, plano de ação, atas, diagramas
│
├── ml/                            # Subprojeto de Machine Learning (Python)
│   ├── README.md
│   ├── pyproject.toml             # (a criar) — deps de ML
│   ├── configs/                   # YAMLs de experimentos (1 arquivo = 1 experimento reproduzível)
│   ├── data/                      # Datasets (gitignored)
│   │   ├── raw/
│   │   │   ├── public_datasets/   # irCNN, AAU VIRADA, Rain_CCTV, etc.
│   │   │   └── imt_coleta/        # Coleta própria no IMT
│   │   ├── processed/             # Frames extraídos + labels alinhados
│   │   ├── splits/                # train/val/test (split por evento, não por frame)
│   │   └── synthetic/             # Augmentação sintética
│   ├── notebooks/                 # Exploração e comparações
│   ├── src/cityrain_ml/
│   │   ├── data/                  # Loaders, transforms, augmentação
│   │   ├── models/                # Arquiteturas candidatas (todas — nenhuma fechada)
│   │   ├── training/              # Loops, losses, schedulers, callbacks
│   │   ├── evaluation/            # Métricas (acurácia, F1, matriz de confusão), comparação contra estações
│   │   ├── optimization/          # Quantização, pruning, export ONNX/TensorRT
│   │   └── utils/                 # Logging, seed, sincronização câmera ↔ estação
│   ├── checkpoints/               # Pesos treinados (gitignored — exportar ONNX para o backend)
│   ├── scripts/                   # Download de datasets, extração de frames, demos
│   └── tests/
│
├── backend/                       # Subprojeto da API (Python)
│   ├── README.md
│   ├── pyproject.toml             # (a criar) — FastAPI, Uvicorn, SQLAlchemy, Alembic, h3, httpx
│   ├── .env.example               # (a criar) — DATABASE_URL, etc.
│   ├── app/
│   │   ├── api/                   # Routers HTTP (endpoints REST)
│   │   ├── core/                  # Config, settings, logging
│   │   ├── db/                    # Models SQLAlchemy + sessão
│   │   ├── ingestion/             # Clients CGE-SP / INMET / CEMADEN + jobs de ingestão
│   │   ├── inference/             # Carrega modelo ONNX exportado pelo ml/ e infere
│   │   ├── h3/                    # Conversão lat/lng → célula H3, agregação por célula
│   │   └── schemas/               # Pydantic
│   ├── migrations/                # Alembic
│   └── tests/
│
└── frontend/                      # Subprojeto do Dashboard (React + Vite + Tailwind)
    ├── README.md
    ├── package.json               # Vite + React + Tailwind + Recharts + Leaflet + react-router-dom
    ├── vite.config.js
    ├── tailwind.config.js
    ├── postcss.config.js
    ├── eslint.config.js
    ├── index.html
    ├── public/
    └── src/
        ├── main.jsx               # Entry point
        ├── App.jsx                # Roteamento (Landing ↔ Dashboard)
        ├── index.css / App.css    # Estilos globais + Tailwind
        ├── assets/                # hero.png, ícones
        ├── components/
        │   ├── ui/                # Componentes atômicos reutilizáveis (CategoryBadge, StatusDot)
        │   ├── layout/            # Topbar
        │   ├── landing/           # Hero, Features
        │   └── dashboard/         # KPICards, RainfallChart, HeatMap, UrbanMap,
        │                          # AlertsPanel, ClassificationCards, ReadingsTable
        ├── pages/                 # Landing.jsx, Dashboard.jsx
        ├── hooks/                 # useRainfallData.js, useClassificationData.js
        ├── api/                   # (a criar) — cliente HTTP do backend
        └── lib/                   # Utilitários: categories.js, mockData.js
                                   # (dados reais virão via api/ quando o backend estiver pronto)
```

**Comunicação entre subprojetos:**
- `ml/` → exporta modelo (ex: ONNX) → consumido por `backend/app/inference/`
- `backend/` → expõe API HTTP → consumida por `frontend/src/api/`
- `backend/` → ingere de APIs públicas (CGE-SP, INMET, CEMADEN) → grava em Postgres

## Convenções de Código

- Seguir PEP 8 para Python
- Type hints em funções públicas
- Docstrings formato Google style
- Nomes de variáveis em inglês, comentários podem ser em português
- Commits em português: `tipo: descrição` (feat, fix, docs, refactor, test, exp)
- Branches: `main`, `develop`, `exp/nome-do-experimento`
- Cada experimento deve ser reproduzível a partir de um config YAML

## Contexto para o Claude

- Este é um TCC de graduação — manter complexidade viável no prazo
- Documentação final segue normas ABNT
- **Decisões fechadas:**
  - Saída atual do modelo: **classificação em 4 classes** (`seco`, `garoa`, `moderada`, `forte`). Regressão mm/h só após validar a classificação.
  - **Sem pluviômetro embarcado** — ground truth vem de **estações públicas** (CGE-SP, INMET, CEMADEN).
  - **Stack de backend:** FastAPI + Uvicorn + PostgreSQL + H3. API REST/HTTP entre frontend e backend, e HTTP entre backend e APIs públicas.
  - **Plataforma embarcada de referência:** NVIDIA Jetson Nano.
  - **Coleta veicular** pela Região Metropolitana de SP + ABC Paulista (não fixa).
  - **Frontend:** React (JSX) + Vite + Tailwind CSS. Stack inicializada e migrada para `frontend/` em maio/2026. Componentes em JSX (não TypeScript por ora). Dados reais ainda via mock (`lib/mockData.js`) — integração com o backend fica em `src/api/` quando a API estiver pronta.
  - **Sem V2X.** A entrega é o dashboard urbano.
- **Decisões abertas (continuar tratando como experimento):** framework de ML, arquitetura do modelo, abordagem física vs. ML vs. híbrida, técnicas de pré-processamento, **protocolo Jetson → Backend (HTTP vs MQTT)**.
- Quando sugerir algo na parte aberta, apresentar como "candidato a testar" e oferecer alternativas
- Priorizar código que facilite experimentação e comparação entre abordagens
- A coleta é **móvel** (veículo percorrendo SP + ABC Paulista), portanto o fundo é dinâmico — considerar isso em pré-processamento e na escolha de arquiteturas (modelos temporais ganham peso)
- Quando gerar código, incluir type hints e docstrings
- Preferir soluções simples e reproduzíveis sobre complexidade desnecessária
- O orientador quer foco na qualidade da experimentação e comparações na parte de modelo