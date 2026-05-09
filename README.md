# CityRain

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql)
![H3](https://img.shields.io/badge/H3-spatial%20index-orange)
![IMT](https://img.shields.io/badge/Instituição-IMT%20Mauá-red)

> **Sistema de monitoramento pluviométrico urbano por visão computacional.** Classifica a intensidade da chuva (`seco`, `garoa`, `moderada`, `forte`) a partir de imagens de câmera e visualiza o resultado em um dashboard web em tempo real, agregado espacialmente em células hexagonais H3.

**Título formal:** CityRain — Sistema Embarcado de Monitoramento Climático Urbano por Visão Computacional
**Trabalho de Conclusão de Curso** — Ciência da Computação, Centro Universitário do Instituto Mauá de Tecnologia (IMT)

---

## Visão Geral

A maior parte dos sistemas de visão para chuva responde apenas *"está chovendo?"*. O CityRain dá um passo além e produz uma **classificação em 4 níveis de intensidade** diretamente da imagem da câmera, sem depender de pluviômetro embarcado. A saída é consumida por um dashboard web que mostra, em tempo real, a intensidade da chuva em diferentes pontos da cidade.

### O que é decidido vs. o que continua aberto

| Área | Status |
|---|---|
| **Saída do modelo** | **Decidido (escopo atual):** classificação em 4 classes (`seco`, `garoa`, `moderada`, `forte`). Regressão em mm/h é objetivo futuro, condicional aos resultados da classificação. |
| **Ground truth** | **Decidido:** pluviômetros públicos urbanos (CGE-SP, INMET, CEMADEN). Sem pluviômetro embarcado da equipe. |
| **Backend** | **Decidido:** FastAPI + Uvicorn + PostgreSQL + H3, integração via HTTP. |
| **Frontend** | **Decidido:** React + TypeScript. |
| **Framework de ML** | **Aberto** — em fase de experimentação (PyTorch / TensorFlow / outro). |
| **Arquitetura do modelo** | **Aberto** — comparando candidatos (CNNs leves, detectores de estágio único, abordagens híbridas com física). |
| **Abordagem** | **Aberto** — detecção de gotas + modelagem física **vs.** regressão direta via CNN **vs.** híbrida. |

> **Importante:** o modelo recebe **apenas a imagem** em inferência. As estações públicas servem só para (1) gerar labels do dataset durante o treino e (2) validar a predição durante a avaliação.

---

## Arquitetura

```
┌──────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  Câmera  │──▶│ Pré-process. │──▶│   Modelo     │──▶│   Backend    │──▶│  Frontend    │
│  (RGB)   │   │              │   │  (CNN/...)   │   │  FastAPI     │   │  React       │
└──────────┘   └──────────────┘   └──────────────┘   │  + Postgres  │   │  + mapa H3   │
                                          │          │  + H3        │   └──────────────┘
                                          ▼          └──────────────┘
                                    [classe 4 níveis]         ▲
                                                              │
                                            ┌─────────────────┴─────────────────┐
                                            │  Estações públicas (offline only) │
                                            │  CGE-SP / INMET / CEMADEN         │
                                            │  → labels de treino + validação   │
                                            └───────────────────────────────────┘
```

### Camadas

| Camada | Responsabilidade |
|---|---|
| **`ml/`** | Treinar, avaliar e exportar o modelo de classificação (Python) |
| **`backend/`** | API HTTP, ingestão de estações públicas, persistência, agregação H3 (Python) |
| **`frontend/`** | Dashboard de visualização em tempo real (React + TypeScript) |
| **`docs/`** | Documento do TCC (ABNT), referências, planejamento |

---

## Estrutura do Repositório

```
cityrain/
├── CLAUDE.md          # Contexto do projeto para o Claude Code (versionado)
├── README.md
├── .gitignore
├── docs/              # TCC, referências, plano de ação, atas, diagramas
├── ml/                # Subprojeto de Machine Learning (Python)
├── backend/           # Subprojeto da API (Python — FastAPI + Postgres + H3)
└── frontend/          # Subprojeto do Dashboard (React + TypeScript)
```

Cada subprojeto tem seu próprio `README.md` com detalhes da estrutura interna, stack e instruções de execução.

---

## Objetivos do Projeto

1. Investigar e comparar técnicas de pré-processamento para isolamento de regiões de interesse (gotas, distorções ópticas).
2. Treinar e avaliar modelos CNN candidatos para **classificação em 4 níveis**, estabelecendo baselines de precisão e latência.
3. Implementar e otimizar detectores de estágio único para detecção contínua em tempo real.
4. Investigar viabilidade futura de estimativa quantitativa em mm/h (regressão), condicional aos resultados da classificação.
5. Implantar modelo otimizado em hardware de borda com quantização e fusão de camadas.
6. Construir backend de ingestão e agregação espacial integrando inferências da câmera e estações públicas via HTTP.
7. Desenvolver dashboard React para visualização em tempo real (mapa H3 + séries temporais).
8. Avaliar viabilidade da solução vs. métodos tradicionais (precisão, latência, custo).

---

## Métricas de Avaliação

### Fase atual — classificação 4-classes
- Acurácia geral e por classe
- Matriz de confusão (`seco` × `garoa` × `moderada` × `forte`)
- F1-score macro e por classe
- Recall em `forte` (crítico para alertas)

### Performance de edge
- Latência por frame (ms)
- Throughput (FPS)
- Uso de memória (MB)
- Degradação de acurácia pós-quantização

### Fase futura — regressão mm/h (condicional)
- MAE, MAPE, R², NSE, KGE

---

## Equipe

| Nome | RA |
|---|---|
| Rodrigo Monteiro Toffoli Teixeira | 23.00068-6 |
| Guilherme Mattioli | 20.00599-7 |
| Gabriel Moreno | 23.01528-4 |
| Paulo Vespero | 23.00607-2 |

**Orientador:** Prof. Gabriel de Souza Lima
**Instituição:** Centro Universitário do Instituto Mauá de Tecnologia (IMT)
**Cronograma:** março–novembro de 2026

---

## Citação

```bibtex
@thesis{cityrain2026,
  title   = {CityRain: Sistema Embarcado de Monitoramento Climático Urbano por Visão Computacional},
  author  = {Teixeira, Rodrigo M. T. and Mattioli, Guilherme and Moreno, Gabriel and Vespero, Paulo},
  school  = {Centro Universitário do Instituto Mauá de Tecnologia},
  year    = {2026},
  advisor = {Lima, Gabriel de Souza}
}
```

---

## Licença

MIT. Ver [LICENSE](LICENSE).
