# ml/ — Dados, treino e avaliação

Tudo o que produz os modelos do CityRain: coleta e rotulagem das imagens, treino, avaliação honesta e exportação para ONNX, consumido pelo `backend/`. Em produção o modelo recebe **só a imagem**; pluviômetros e radar servem apenas para rotular o treino e medir o resultado.

## Modelos em produção

| Modelo | Arquitetura | Classes | Receita |
|---|---|---|---|
| Intensidade do carro (v14f) | MobileNetV3-Large, 288×384, 13 blocos congelados | garoa · moderada · forte | `configs/treino_intensidade_final_v14f_limpo_dia_mnv3.yaml` |
| Intensidade da câmera fixa | MobileNetV3-Large, 288×384 | seco · garoa · moderada · forte | `configs/treino_fixa_f1_mnv3.yaml` (via `rodar_experimentos_fixa.py`) |
| Gate da Jetson | MobileNetV2, 384×384 | com gota · sem gota | `scripts/treino/treinar_gate_v2.py` |

Números, protocolo e histórico de todas as versões: [`docs/resultados-experimentos.md`](../docs/resultados-experimentos.md).

## Princípios

- **Rótulo vem de instrumento:** pluviômetro CEMADEN (Brasil) ou radar NOAA MRMS (EUA), com regra de concordância no espaço (3×3 células) e no tempo (±2 min). A revisão visual só exclui imagem defeituosa, nunca muda classe.
- **Split por evento, nunca por frame:** frames do mesmo dia de chuva nunca ficam em treino e teste ao mesmo tempo. A validação cruzada segura grupos de eventos do irCNN e de para-brisa.
- **Teste é sempre dado real.** Sintético foi abandonado em 14/10/2026.
- **1 YAML = 1 experimento reproduzível.** Cada run grava a config usada, o histórico e as predições por partição.

## Estrutura

```
ml/
├── configs/                 # um YAML por experimento (CV e finais)
├── src/cityrain_ml/
│   ├── data/                # datasets e pré-processamento (o mesmo do backend)
│   ├── training/            # treino e CV por evento (intensidade, câmera fixa)
│   ├── evaluation/          # métricas: F1 macro, ordenação, Spearman, IC por bootstrap
│   └── models/              # fábrica de arquiteturas e híbrido CNN + atributos físicos
├── scripts/
│   ├── captura/             # código que roda na Jetson (Python 3.6) e replay de demonstração
│   ├── sessao_carro/        # sessão gravada no carro → frames rotulados pelo CEMADEN
│   ├── coleta_fixa/         # coletor das lives, DVR, replay de evento
│   ├── estacoes/            # CEMADEN, CGE-SP e INMET normalizados
│   ├── bdd/ · dataset_mapillary/ · dataset_youtube/   # para-brisa rotulado por radar MRMS
│   ├── dataset/             # montagem dos splits
│   ├── treino/              # treinar, exportar ONNX, roteiro da câmera fixa
│   └── avaliacao/           # IC, baseline físico, Grad-CAM, rótulos suspeitos, checador do modelo fixo
├── resultados/              # resumos versionados (JSON/CSV) que sustentam o texto
├── tests/                   # pytest (rodado no CI)
└── data/ · runs/            # imagens, splits e runs: fora do Git
```

## Ambiente

```bash
python3 -m venv ml/.venv
ml/.venv/bin/pip install -r ml/requirements-treino.txt   # torch, onnx, onnxruntime, yt-dlp + o do CI
```

Testado com Python 3.12–3.14, PyTorch 2.14 (MPS no Mac M-series; CUDA se houver GPU NVIDIA).

## Comandos principais

```bash
# validação cruzada por evento (imprime irCNN, para-brisa, ordenações)
ml/.venv/bin/python ml/scripts/treino/treinar_intensidade.py ml/configs/treino_intensidade_cv_v14f_limpo_dia_mnv3.yaml --cv

# modelo final (todos os eventos no treino) e exportação com paridade PyTorch × ONNX
ml/.venv/bin/python ml/scripts/treino/treinar_intensidade.py ml/configs/treino_intensidade_final_v14f_limpo_dia_mnv3.yaml --fold final
ml/.venv/bin/python ml/scripts/treino/exportar_onnx.py ml/runs/<run>/melhor.pt --saida backend/app/inference/modelos/intensidade.onnx

# câmera fixa: diagnóstico, CV, escolha e final em um roteiro
ml/.venv/bin/python ml/scripts/treino/rodar_experimentos_fixa.py checar

# sessão gravada no carro → frames normalizados e rotulados
ml/.venv/bin/python ml/scripts/sessao_carro/processar_sessao.py /caminho/da/sessao --rotacao 180
```

Guias passo a passo: [`GUIA-SESSAO-CARRO`](../docs/GUIA-SESSAO-CARRO.md), [`GUIA-COLETA-EQUIPE`](../docs/GUIA-COLETA-EQUIPE.md), [`GUIA-TREINO-EQUIPE`](../docs/GUIA-TREINO-EQUIPE.md).

## Segredos

`ml/.env` (token do Mapillary), `ml/configs/coleta_fixa_tokens.json` (tokens das câmeras) e `ml/scripts/captura/cityrain_config.json` (token da Jetson) estão no `.gitignore` e nunca devem ser commitados. Os formatos estão em `ml/.env.example`, `ml/configs/coleta_fixa_tokens.example.json` e `ml/scripts/captura/cityrain_config.example.json`.

## Testes

```bash
ml/.venv/bin/python -m pytest -q ml/tests
```
