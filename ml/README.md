# ml/ — Machine Learning

Subprojeto responsável por **treinar, avaliar e exportar** o modelo de classificação de intensidade de chuva (`seco`, `garoa`, `moderada`, `forte`) a partir de imagens de câmera.

> **Importante:** este subprojeto produz um **artefato exportado** (ex: ONNX) que é consumido pelo `backend/`. Em inferência (produção), o modelo recebe **apenas a imagem** — não consulta estação meteorológica. As estações públicas (CGE-SP, INMET, CEMADEN) entram só em (1) gerar labels do dataset e (2) avaliar a predição.

## Estrutura

```
ml/
├── configs/                # YAMLs de experimentos (1 arquivo = 1 experimento reproduzível)
├── data/                   # Datasets (gitignored — usar DVC, link simbólico ou storage externo)
│   ├── raw/
│   │   ├── public_datasets/  # irCNN, AAU VIRADA, Rain_CCTV, etc.
│   │   └── imt_coleta/       # Coleta própria no campus do IMT
│   ├── processed/          # Frames extraídos + labels já alinhados
│   ├── splits/             # train / val / test (split por evento, não por frame)
│   └── synthetic/          # Sinteticos (rain streaks, augmentação)
├── notebooks/              # Exploração, visualização, comparações
├── src/cityrain_ml/
│   ├── data/               # Datasets, loaders, transforms, augmentação
│   ├── models/             # Arquiteturas candidatas (todas — nenhuma fechada)
│   ├── training/           # Training loops, losses, schedulers, callbacks
│   ├── evaluation/         # Métricas (acurácia, F1, matriz de confusão), comparação contra estações
│   ├── optimization/       # Quantização, pruning, exportação ONNX/TensorRT
│   └── utils/              # Logging, seed, sincronização temporal câmera ↔ estação
├── checkpoints/            # Pesos treinados (gitignored)
├── scripts/                # download de datasets, extração de frames, demos
└── tests/
```

## Stack

- **Aberto:** framework de ML (PyTorch / TensorFlow / outro), arquitetura do modelo, abordagem (física / ML / híbrida)
- **A definir conforme experimentação avança**

## Como rodar (placeholder)

A definir após escolha do framework. Sugestão inicial:

```bash
cd ml
python -m venv .venv && source .venv/bin/activate
pip install -e .
python scripts/train.py --config configs/baseline.yaml
```
