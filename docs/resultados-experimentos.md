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
| CV v6: v3 **sem sintético** (`treino_intensidade_cv_v6_sem_sint_mnv3.yaml`) | 0,419 | 0,058 / 0,431 / 0,767 | 0,45 | 1,000 | 0,554 | 0,968 | 0,339 |
| Baseline físico (régua + reg. logística) | 0,402 | 0,044 / 0,435 / 0,728 | 0,46 | 0,895 | **0,875** | 0,783 | **0,669** |

\* v1 testado no irCNN inteiro (não é CV); as demais são agregadas dos 4 folds.

**Modelo de produção** (`treino_intensidade_final_v3_mnv3.yaml`: desenho da v3, todos os
eventos irCNN, 7 épocas fixas = mediana da CV): garoa 13/09 157/157; 23/09 > 13/09 0,645;
YouTube > 13/09 0,978; pico > início 0,694. A estimativa de desempenho no irCNN é a da CV v3.

### Intervalos de confiança (bootstrap por evento, 12 eventos, 1.000 reamostras, IC 95%)

| Versão | irCNN F1 macro | F1 forte | Spearman |
|---|---|---|---|
| v1 | 0,458 [0,411; 0,491] | 0,803 [0,715; 0,852] | 0,595 [0,456; 0,673] |
| v2 | 0,428 [0,356; 0,481] | 0,792 [0,708; 0,851] | 0,603 [0,394; 0,744] |
| **v3** | **0,462 [0,401; 0,507]** | **0,817 [0,724; 0,876]** | **0,638 [0,421; 0,751]** |
| v4 | 0,449 [0,361; 0,505] | 0,783 [0,600; 0,869] | 0,554 [0,367; 0,682] |
| v5 | 0,419 [0,350; 0,466] | 0,771 [0,653; 0,842] | 0,596 [0,405; 0,700] |
| v6 (sem sintético) | 0,419 [0,336; 0,476] | 0,767 [0,662; 0,839] | 0,445 [0,228; 0,599] |

Diferenças **pareadas** (mesmos eventos sorteados), F1 macro: v3−v2 +0,032 [+0,002; +0,069];
v3−v5 +0,044 [+0,016; +0,074] → v3 **significativamente melhor** que v2 e v5. v3−v1 +0,003
[−0,035; +0,047] e v3−v4 +0,016 [−0,033; +0,076] → **empate estatístico** no irCNN; a
vantagem da v3 sobre a v1 está na ordenação do YouTube (pico > início 0,61 × 0,32). O efeito
grande e inequívoco é **irCNN no treino** (0,07 → ~0,46). (`ml/resultados/intervalos_confianca.json`)

**Sintético × sem sintético (v3 × v6, pareado, 2.000 reamostras):** v3−v6 F1 macro +0,045 [+0,014; +0,082]; Spearman +0,172 [−0,027; +0,364]. Retirar o sintético **piora** o F1 macro de forma significativa (IC não inclui 0) e, nas métricas ordinais, derruba 23/09 > 13/09 (0,685 → 0,554) e pico > início no YouTube (0,605 → 0,339); garoa 13/09 e YouTube > 13/09 não mudam (1,000 e 0,968). Veredito: **v6 é pior que a v3** — o sintético (moderada/forte de para-brisa) ajuda e **não deve sair** do modelo do carro. Nota: no val de v6 o domínio "próprio" fica em 0,167 (o val tem moderada/forte sintéticas, que o modelo sem sintético nunca viu), então o critério de escolha de época ficou dominado pelo irCNN; a comparação com a v3 mantém-se válida (mesmos folds, mesmo critério). (`ml/runs/treino_cv_v6.log`)

### Leituras

1. **Domínio manda mais que arquitetura.** Sem irCNN no treino, o modelo aprende "gota no
   para-brisa" e não reconhece chuva em câmera fixa (0,07). Com eventos irCNN no treino, 0,46.
2. **Atalho de domínio corrigido:** com 59 garoas do irCNN no treino, "cara de irCNN ⇒ não é
   garoa" (garoa 0,02); amostrar por (evento, classe) eleva a 404 e melhora ordenação (v3).
3. **Resultados negativos:** sintético por película (v2), resolução maior (v4) e garoa extra de
   câmera fixa (v5) não melhoram. Falta **moderada/forte real**, não pixel nem garoa.
4. **Garoa em câmera fixa é praticamente invisível** (F1 ≤ 0,06 em todas as versões, mediana
   1,1 mm/h). Limitação a declarar.
5. **Sem atalho de carimbo:** borrar o carimbo de data/hora e o rodapé de 900 frames do irCNN
   mantém 96,8% das predições (F1 0,868 → 0,856) — o modelo não usa o texto da câmera
   (`ml/scripts/avaliacao/checar_carimbo.py`). Grad-CAM (`ml/resultados/figuras/gradcam_v3_vs_v1.jpg`):
   no irCNN a v3 olha névoa (dia) e riscos iluminados (noite); na nossa câmera, asfalto molhado
   e reflexos.
6. **Híbrido (CNN + físico, ensemble de probabilidades, peso escolhido NA VALIDAÇÃO = 0,95):**
   irCNN 0,463 [0,403; 0,508] (= CNN), Spearman 0,645, **23/09 > 13/09 0,685 → 0,855**, YouTube >
   13/09 0,966, pico > início 0,626, garoa 13/09 0,979. Ganho de ordenação no para-brisa sem
   perda nas demais. Ressalva: a validação não tem dado ordinal e quase não distingue os pesos
   (critério 0,8156 com e sem físico) — escolha legítima, mas pouco informada
   (`ml/scripts/avaliacao/ensemble_hibrido.py`).
7. **CNN × físico:** a CNN classifica melhor (+0,06 F1, +0,18 Spearman), mas o baseline físico
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

### 4.1 Limiar do gate e gate v2 por sessão (13/10/2026)

**Limiar (gate original, produção = 0,5).** Os pesos `bestModel` só existem na Jetson, que
estava indisponível; a curva completa 0,02–0,5 não foi feita. Os pontos que já existiam
(`ml/runs/gate_v2/gate_v2.json`, "antes"): limiar 0,5 → recall 13/09 0,10, 23/09 0,36, falso
alarme 06/08 0,17; limiar 0,2 → 0,18 / 0,41 / 0,17. AUC chuva × seco noite = 0,53 (quase
acaso). Baixar o limiar quase não ajuda e o falso alarme noturno não muda: o gate original não
separa chuva de seco nas nossas sessões, então a troca de limiar sozinha não resolve.

**Gate v2 (`ml/scripts/treino/treinar_gate_v2.py cv`).** Validação leave-one-session-out em
6 folds (1 sessão seca × 1 de chuva fora do treino: seco 04/08, 06/08; chuva 01/09, 13/09,
23/09), 3 épocas, MobileNetV2 384², brilho aleatório forte nas duas classes. Dado externo
RaindropsOnWindshield (Zenodo): `1o/2o/8o` (máscaras vazias, vidro limpo, 450 imagens) como
seco e `D2`/`v2` (gotas, 400 imagens) como chuva; `D1` descartada (gota em 2,6% fixos).
Resultado em limiar 0,5 (recall chuva / falso alarme seco, ambos em sessão não vista):

| Seco fora | Chuva fora | ImageNet + externo | Ajuste v1 + externo | ImageNet sem externo |
|---|---|---|---|---|
| 04/08 | 01/09 | 1,00 / 1,00 | 0,99 / 0,92 | 1,00 / 1,00 |
| 04/08 | 13/09 | 0,81 / 1,00 | 0,97 / 0,82 | 0,97 / 1,00 |
| 04/08 | 23/09 | 0,77 / 1,00 | 0,77 / **0,22** | 0,90 / 1,00 |
| 06/08 | 01/09 | 0,67 / 0,95 | 0,90 / 0,97 | 0,70 / 0,95 |
| 06/08 | 13/09 | 1,00 / 0,95 | 1,00 / 1,00 | 1,00 / 0,94 |
| 06/08 | 23/09 | 0,94 / 0,83 | 0,96 / 0,98 | 0,96 / 0,67 |

**Não bate o original** (falso alarme 0,17 no seco noite em 0,5): na maioria dos folds o
falso alarme fica em 0,8–1,0, e quando 04/08 sai do treino o AUC chega a 0,04–0,09 (inverte:
o modelo aprendeu "vidro da nossa câmera = chuva"). Com só 2 sessões secas, tirar uma deixa
uma única sessão seca da nossa câmera no treino. O dado externo não corrige isso (o único
fold bom, 04/08 × 23/09 com 0,22, é um fold, não um padrão; com ajuste v1 já como ponto de
partida). Conclusão: nenhum gate v2 é exportado; o gate original continua em produção. O
gargalo é seco da câmera do carro (dia e noite, várias sessões), não treino. Observação:
`framesSemNada` (27/05) **não é seco**: tem chuva forte à noite, sem rótulo de pluviômetro.
Resultados: `ml/resultados/gate_v2_cv_*.json`.

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
