# Resultados dos experimentos — rascunho para o capítulo de resultados

> Consolidado em 05/10/2026. Todos os números saem de `ml/runs/` e `ml/resultados/`
> (gitignored os runs; os resumos em `ml/resultados/` são versionados). Cada linha aponta
> o config que a reproduz.

## 1. Protocolo

- **Rótulo:** mm/h de pluviômetro público (CEMADEN), nunca do olho. Classes: seco = 0;
  garoa ≤ 2,5; moderada ≤ 10; forte > 10 mm/h (`ml/configs/rotulagem_imt.yaml`).
- **Modelo de intensidade** (garoa | moderada | forte; `seco` é do gate na Jetson):
  MobileNetV3-Large ImageNet, ajuste fino completo, 288×384.
- **Validação cruzada por evento no irCNN** (12 eventos, câmera fixa com pluviômetro):
  4 folds declarados de 3 eventos; cada evento é testado só quando está fora do treino.
- **Sintético nunca entra em teste.** Testes reais: garoa da nossa câmera (13/09, sessão
  nunca vista) e irCNN; ordinais: 23/09 (6–19 mm/h por perto) e vídeos YouTube de chuva forte.
- **Ordenação** = P(score do grupo mais intenso > score do menos intenso), score = classe esperada.

## 2. Modelo de intensidade — todos os experimentos

| Experimento (config) | irCNN F1 macro | garoa / mod. / forte | Spearman score×mm/h | Garoa 13/09 (F1) | 23/09 > 13/09 | YouTube > 13/09 | YouTube pico > início |
|---|---|---|---|---|---|---|---|
| Constante "garoa" (referência) | 0,022 | — | — | 1,000 | — | — | — |
| v1: sintético, sem irCNN no treino* | 0,074 | — | 0,06 | 0,997 | 0,841 | 0,927 | 0,264 |
| CV v1: + irCNN por evento | 0,458 | 0,025 / 0,546 / 0,803 | 0,59 | 0,996 | 0,744 | 0,961 | 0,317 |
| CV v2: sintético forte por película | 0,428 | 0,010 / 0,482 / 0,792 | 0,61 | 0,975 | 0,647 | 0,977 | 0,369 |
| **CV v3: + irCNN por (evento, classe)** | **0,462** | 0,055 / 0,516 / **0,817** | **0,64** | 0,992 | 0,685 | 0,958 | 0,605 |
| CV v4: v3 em 480×640 | 0,449 | 0,036 / 0,527 / 0,783 | 0,55 | 0,988 | 0,594 | 0,932 | 0,542 |
| CV v5: v3 + lives (câmera fixa real) | 0,419 | 0,045 / 0,440 / 0,771 | 0,59 | 0,988 | 0,660 | 0,734 | 0,367 |
| Baseline físico (régua + reg. logística) | 0,402 | 0,044 / 0,435 / 0,728 | 0,46 | 0,895 | **0,875** | 0,783 | **0,669** |

\* v1 testado no irCNN inteiro (não é CV); as demais são agregadas dos 4 folds.

**Modelo de produção** (`treino_intensidade_final_v3_mnv3.yaml`: desenho da v3, todos os
eventos irCNN, 7 épocas fixas = mediana da CV): garoa 13/09 157/157; 23/09 > 13/09 0,645;
YouTube > 13/09 0,978; pico > início 0,694. A estimativa de desempenho no irCNN é a da CV v3.

### Leituras

1. **Domínio manda mais que arquitetura.** Sem irCNN no treino, o modelo aprende "gota no
   para-brisa" e não reconhece chuva em câmera fixa (0,07). Com eventos irCNN no treino, 0,46.
2. **Atalho de domínio corrigido:** com 59 garoas do irCNN no treino, "cara de irCNN ⇒ não é
   garoa" (garoa 0,02); amostrar por (evento, classe) eleva a 404 e melhora ordenação (v3).
3. **Resultados negativos:** sintético por película (v2), resolução maior (v4) e garoa extra de
   câmera fixa (v5) não melhoram. Falta **moderada/forte real**, não pixel nem garoa.
4. **Garoa em câmera fixa é praticamente invisível** (F1 ≤ 0,06 em todas as versões, mediana
   1,1 mm/h). Limitação a declarar.
5. **CNN × físico:** a CNN classifica melhor (+0,06 F1, +0,18 Spearman), mas o baseline físico
   ordena melhor no para-brisa (23/09: 0,875 × 0,685) — argumento para a abordagem híbrida.

## 3. Domínio do carro (validação da proposta)

- Sessões com rótulo de estação: 01/09, 13/09 (garoa) e 23/09. Correlação score × mm/h ao
  longo das sessões **não informa**: 454 de 492 frames entre 1 e 2,5 mm/h (sem variação).
  O modelo prevê garoa em 99% — correto para essas sessões
  (`ml/scripts/avaliacao/correlacao_sessoes.py`).
- **Câmera fixa nunca vista (Balneário Camboriú, DVR, rótulo de estação):** produção v3 acerta
  248/250 garoa e 5/20 moderada.
- Moderada/forte reais **no para-brisa com rótulo**: inexistentes até aqui (pendência de coleta).

## 4. Gate binário (Jetson)

| | Recall garoa 13/09 | Recall chuva 23/09 | Falso alarme seco noite (06/08) |
|---|---|---|---|
| Gate original (limiar 0,5) | 0,10 | 0,36 | 0,17 |
| Gate com ajuste fino (só 04/08 seco) | 1,00 | 0,88 | **0,98** ❌ |

O gate original descarta a maior parte da chuva real; o ajuste fino decorou "04/08 de dia =
seco". Falta seco diverso (dia e noite) — pendência de coleta, não de modelo.

## 5. Borda (Jetson Nano 4 GB, onnxruntime 1.10, 60 frames reais)

| Modelo | Execução | Inferência (mediana) | Total c/ pré-proc. | FPS |
|---|---|---|---|---|
| Gate MobileNetV2 384² | CPU / CUDA | 236 / 57 ms | 280 / 91 ms | 3,6 / 11,0 |
| Intensidade MobileNetV3 288×384 | CPU / CUDA | 174 / 40 ms | 205 / 71 ms | 4,9 / 14,1 |

Captura é 1 fps: folga de 3,6× a 14×. Gate + intensidade em CUDA ≈ 160 ms/frame — a
classificação completa cabe na placa.

**Quantização** (`ml/resultados/quantizacao_20261005.json`): FP16 = 8,4 MB, concordância com
FP32 ≥ 99,5% (sem perda; mesma latência sem TensorRT). INT8 PTQ = 4,7 MB, mas concordância
~0,5 fora do domínio próprio — rejeitado (MobileNetV3 pede QAT).

## 6. Sistema ponta a ponta

Verificado em produção em 05/10/2026: Jetson (gate) → `POST /api/v1/ingest` (Railway) →
ONNX v3 no backend → PostgreSQL → `/captures` e `/stats/geo` (H3) → dashboard React.

## 7. Pendências para fechar o capítulo

1. Moderada/forte reais no carro (saídas em chuva, ou piloto de chuva simulada —
   `docs/protocolo-piloto-chuva-simulada.md`).
2. Sessões secas de dia e noite (para refazer o gate).
3. Câmera conectada na Jetson: medir o pipeline completo em fluxo contínuo.
4. Abordagem híbrida (CNN + atributos físicos) — experimento seguinte.
