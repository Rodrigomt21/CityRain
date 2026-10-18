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

### Sem sintético, só de dia: v6 × v7 com BDD100K (15/10/2026)

Decisões de 14–15/10: o orientador rejeitou o sintético e a noite saiu do escopo do modelo do carro.
Por isso as duas CVs abaixo usam **só os eventos diurnos do irCNN** (1–6, em 3 folds de 2) e não são
diretamente comparáveis às linhas v1–v6 acima (que têm 12 eventos, dia e noite).

**v7** = v6 + **BDD100K** (dashcam de celular atrás do para-brisa, NY/Califórnia) **de dia**, rotulado
por **radar NOAA MRMS PrecipRate** (2 min, ~1 km; outra verdade de campo, não pluviômetro), só rótulos
inequívocos (vizinhança 3×3 e ±2 min concordam). Frames de vídeo a cada 4 s, recorte central 4:3:
926 de moderada (95 vídeos) e 2.864 de garoa (300 vídeos); forte diurna inequívoca no BDD: 0. Todo o BDD
fica no treino; o teste continua irCNN + carro. Pipeline: `ml/scripts/bdd/` (etapas 1–7 +
`montar_split_v7.py`). A busca pelo radar nos 22.883 vídeos que o BDD marcou como nublado/indefinido
achou só 1 moderada diurna inequívoca: o rótulo `rainy` do BDD já cobre quase toda a chuva.

| CV só dia | irCNN F1 macro | F1 moderada | Spearman | 23/09 > garoa 13/09 | YT pico > início | YT > garoa 13/09 | Temporal 10/03/2023 ≥ moderada |
|---|---|---|---|---|---|---|---|
| v6 (sem sintético) | **0,417** | **0,41** | 0,415 | 0,245 | 0,371 | 0,802 | 0–4% |
| **v7 (v6 + BDD dia)** | 0,375 | 0,30 | **0,596** | **0,640** | **0,641** | **0,966** | **40–74%** |

**Temporal 10/03/2023** (teste novo de forte): vídeo do YouTube `qcI7SWTst4I`, celular atrás do
para-brisa, Marginal Pinheiros, de dia; CEMADEN Pinheiros/Centro/Mooca marcou 35–87 mm/h entre 14h30
e 15h20. A hora exata de cada trecho do vídeo não é conhecida, então ele é teste (fração de frames
≥ moderada), não treino. 236 frames, 1 a cada 10 s (`ml/data/processed/youtube/carro_forte_20230310/`).
v3 (com sintético) 97% ≥ moderada (9% forte); v6 0–4%; v7 40–74% nos 3 folds; v7 final 64%. Nenhuma
versão sem sintético prevê forte nele.

**Leitura:** o BDD recupera, sem sintético, a ordenação de intensidade **no domínio do para-brisa**
(23/09 e YouTube voltam ao nível da v3), ao custo de ~0,04 de F1 no irCNN (câmera de vigilância, fora
do domínio). Falta forte de para-brisa: só uma sessão real em temporal fecha esse buraco.

**v7 final** (`treino_intensidade_final_v7_bdd_dia_mnv3.yaml`, 8 épocas = mediana da CV 5/8/11, fica a
última): garoa 13/09 1,000; YT pico > início 0,705; 23/09 > garoa 0,581; YT > garoa 0,836; temporal
64% ≥ moderada. ONNX em `ml/runs/intensidade_final_v7_bdd_dia_mnv3_foldfinal__20261015_231604/intensidade_v7.onnx`
(paridade PyTorch × ORT 2,6e-6). A v6 final (piso, sem BDD) ficou em 0,285 / 0,263 / 0,940 e 1% no temporal.

### Forte de para-brisa real: dashcam + Mapillary rotulados por radar (16–17/10/2026)

Fontes novas, todas de dia, rótulo MRMS inequívoco (3×3 e ±2 min), horário conferido no relógio
gravado na imagem: **dashcams do YouTube** com GPS/hora na tela (`ml/scripts/dataset_youtube/dashcam_radar.py`)
e **Mapillary** por área (`mapillary_chuva.py`) e **por usuário** (`mapillary_criador.py`: quem já dirigiu
num temporal costuma dirigir na chuva outras vezes). Usuários aprovados na revisão visual: `allen`
(BlackVue, Jacksonville, 7 dias), `cubanoboi` (iPhone dentro do carro, Flórida, 6 dias), `Satsuka_Osaka`
(iPhone, 1 dia) e BlackVue de Savannah 25/08/2023. Descartados: câmera pela janela lateral, carro
parado com vidro seco, neve/gelo no chão.

| CV só dia | Dados novos | irCNN agregado | YT pico > início | 23/09 > garoa | Temporal SP ≥ mod. (forte) |
|---|---|---|---|---|---|
| v7 | — | 0,375 | 0,641 | 0,640 | 57% (0%) |
| v8 | + 491 forte dashcam | 0,395 | 0,274 | 0,637 | 68% (3%) |
| v9 | v8 + 396 forte Mapillary | 0,441 | 0,454 | 0,514 | 70% (4%) |
| v10 | v7 + dashcam + allen (1.117 forte) | 0,481 | 0,618 | 0,440 | 72% (1%) |

**Nota honesta de para-brisa (v11+).** Até a v10 todo o para-brisa ficava no treino, então nada media
o domínio do produto. A chave `dados.parabrisa_cv` faz cada fold segurar também um grupo de eventos de
para-brisa (`test_parabrisa`, agregado no fim da CV). Correção de protocolo junto: o val tem
forte/moderada **sintéticos** (1.048 linhas) e escolhia a época; v11+ usa **6 épocas fixas** na CV e no
final (`sem_selecao_por_val`).

| CV só dia | Para-brisa F1 | Spearman frame / evento | irCNN agreg. | YT pico > início | 23/09 > garoa |
|---|---|---|---|---|---|
| v7 final (nunca viu para-brisa) | 0,167 | 0,29 / 0,12 | — | — | — |
| v11 (v10, 12 eventos de para-brisa) | 0,320 | 0,10 / −0,19 | **0,455** | 0,679 | 0,483 |
| v12 (v11 + 13 blocos congelados) | **0,349** | 0,10 / −0,20 | 0,427 | **0,765** | **0,602** |

**Leitura:** em dia de para-brisa nunca visto, a CNN fica perto do acaso e **não ordena** a intensidade
entre dias (no mesmo carro, um dia de moderada vira forte e um de forte vira moderada): com ~12 dias ela
decora o dia (luz, lugar), não a chuva. Ajustar viés de logit em 2 folds e medir no 3º não ajuda. A
alavanca é **número de dias** de para-brisa, não fotos por dia. Finais: v11 final YT pico > início
0,878 (melhor até aqui), mas temporal SP 46% ≥ moderada (v7 final 64%).

**Atributos físicos no para-brisa** (20 eventos, sem rede): brilho e contraste caem com a chuva
(Spearman por evento −0,67 e −0,59; dark channel −0,50). Regressão linear em log(mm/h) com brilho +
contraste, deixando um dia de fora por vez: Spearman por evento **0,63 (IC 95% 0,28–0,85)**. Mas depende
da câmera: dashcams (allen +0,79, YouTube +0,60) sim, iPhone (cubanoboi −0,58, exposição automática)
não, e em 3 folds com 12 eventos o sinal inverte. Implementação em tensor, exportável no mesmo ONNX:
`ml/src/cityrain_ml/models/hibrido.py`. Fica como candidato a híbrido, não como modelo de produção.

**Opções contra "decorar o dia" (17/10), uma de cada vez sobre a v13 (20 eventos de para-brisa):**

| CV | Para-brisa F1 | Spearman evento | F1 moderada | irCNN | YT pico > início | 23/09 > garoa |
|---|---|---|---|---|---|---|
| v13 (base) | 0,395 | 0,32 | 0,255 | 0,441 | 0,689 | 0,535 |
| A: fotometria forte (saturação, balanço de branco, gama, desfoque) | 0,426 | **0,45** | 0,256 | 0,421 | 0,678 | 0,545 |
| B: amostragem 1/n por evento | 0,396 | 0,25 | 0,268 | 0,374 | 0,613 | 0,508 |
| C: perda ordinal (CE + E[\|k−y\|]) | 0,399 | 0,26 | 0,267 | 0,430 | 0,697 | **0,727** |
| E: sem frames de radar perto dos limiares | 0,401 | 0,30 | **0,308** | 0,433 | 0,713 | 0,565 |
| F: sem rótulos suspeitos no treino | **0,457** | 0,42 | 0,287 | 0,438 | **0,795** | 0,665 |
| v15 = A + C | 0,419 | 0,42 | 0,252 | 0,412 | 0,681 | 0,620 |
| v16 = A + F, 27 eventos | 0,438 | 0,59 | 0,231 | **0,449** | 0,630 | 0,555 |

Média de 5–15 frames seguidos quase não ajuda (+0,01 de F1): o erro é do dia inteiro, não do frame.
Rótulo suspeito (F) = frame em que v13 e v14a, sem ver o dia, dão p < 0,10 à classe do radar (895 de
4.189, 21%; `ml/scripts/avaliacao/marcar_rotulo_suspeito.py`); sai só do treino. Vazamento leve: a lista
veio de modelos que viram os outros folds. Matriz da F no para-brisa: 47% exato, 40% erro de uma classe,
13% garoa↔forte; a moderada é o gargalo (24% de acerto).

**Finais (testes nunca vistos):** v13 temporal 56% ≥ moderada / 22% forte, YT 0,854, 23/09 0,587;
**v14f** 59% / 13%, **YT 0,931**, 23/09 0,586, garoa 13/09 98,7%; v16 55% / 17%, YT 0,716, 23/09 0,437.
v13 em produção pelo PR #32; v14f proposta no PR #33.

**Tentativas finais para a moderada (17/10 noite), nenhuma supera a v14f:** média de probabilidades de 2–4
modelos (melhor ensemble 0,443 < 0,457); viés de logit ajustado em 2 folds e medido no 3º (moderada 0,287 →
0,340, mas F1 macro 0,457 → 0,426); **v17 = F + E** na CV: para-brisa 0,469, moderada 0,385, irCNN 0,448,
23/09 0,686, mas YT 0,717 e Spearman por evento 0,34; na final perde nos testes nunca vistos (YT 0,599,
temporal 45% ≥ moderada / 14% forte, 23/09 0,653, garoa 1,000). Fica a v14f.

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
uma única sessão seca da nossa câmera no treino; o Zenodo sozinho não corrige isso.

**Gate v3: com seco visual de maio como dado só de treino (14/10).** A pasta
`classificador/imagens_brutas` (20/05, mesma câmera, sem GPS) tem ~9,3 mil frames
pré-rotulados `sem_chuva` pelo modelo. Seleção (`ml/scripts/treino/selecionar_gate_maio_seco.py`):
só 20260520 com confiança ≥ 0,8, descarta `motivo` que cita molhado/gota/reflexo, stride 2;
sobram 723 candidatos (498 dia, 225 noite por brilho), usados 250 dia + 250 noite por fold.
20260523 fica fora (pista molhada, gotas). Orientação conferida: já vem em pé, igual às
sessões normalizadas, sem rotação. **Regra de rótulo:** no gate o rótulo é **visual** (vidro
sem gota + pista seca), porque o gate detecta gota; rótulo de intensidade continua só de
pluviômetro. Painéis para conferência: `ml/data/review/gate_maio_seco/painel_*.jpg`
(os 6 painéis amostrados parecem secos; falta o aceite visual do Rodrigo). Maio nunca entra
em teste. Mesmo CV, partindo do ajuste v1 + Zenodo + maio (limiar 0,5; recall / falso alarme):

| Seco fora | Chuva fora | AUC | v3 recall / FA | Original recall / FA |
|---|---|---|---|---|
| 04/08 dia | 01/09 | 0,97 | 0,90 / **0,04** | n/d |
| 04/08 dia | 13/09 | 0,98 | 0,96 / **0,11** | 0,10 / n/d |
| 04/08 dia | 23/09 | 0,98 | 0,90 / **0,04** | 0,36 / n/d |
| 06/08 noite | 01/09 | 0,70 | 0,83 / 0,24 | n/d / 0,17 |
| 06/08 noite | 13/09 | 0,78 | 1,00 / 0,25 | 0,10 / 0,17 |
| 06/08 noite | 23/09 | 0,79 | 0,95 / 0,23 | 0,36 / 0,17 |

Recall sobe de 0,10 / 0,36 para ≥ 0,90 (exceto 01/09 noite, 0,83) em sessão não vista; falso
alarme no seco de dia cai para 0,04–0,11. Na noite o falso alarme é 0,23–0,25, um pouco acima
do original (0,17), com só 103 frames de teste e 225 candidatos de maio à noite no treino.
Partindo do ImageNet (3 folds de 04/08, parciais) o falso alarme ficou em 0,46–0,94: partir do
ajuste v1 importa. Falso alarme é barato (o backend classifica a intensidade depois), então o
trade-off recall × alarme noturno é aceitável; limiar mais alto na noite não foi medido.
Resultados: `ml/resultados/gate_v2_cv_*.json` (`*_maio.json` = com maio).

**Gate v3 exportado:** `ml/runs/gate_v3/gate_v3.onnx` (treino em todas as sessões + Zenodo +
maio, 3 épocas; entrada `input` 1x3x384x384, saída `output` 2 logits, opset 11, índice 1 =
com_gota; fica fora do Git). Os números acima são do CV, o modelo final não tem teste próprio.
Aceite pendente: confirmar visualmente os painéis de maio e testar o onnx numa sessão nova.

*Passos para a Jetson (NÃO executados; Moreno/Rodrigo, com a placa ligada):*
1. No Mac: `scp ml/runs/gate_v3/gate_v3.onnx jetson:/home/jetson/modelo_chuva/gate_v3.onnx`.
2. Na Jetson: `cp ~/modelo_chuva/bestModel.onnx ~/modelo_chuva/bestModel.orig.onnx` (backup).
3. Em `~/cityrain_config.json` (o mesmo do `ml/scripts/captura/`), trocar `modelo_chuva_path`
   para `/home/jetson/modelo_chuva/gate_v3.onnx`; manter `limiar_chuva: 0.5`.
4. Reiniciar o serviço que captura: `sudo systemctl restart citycam` (serviços em
   `implantar_jetson.sh`: citycam, gps, uploader, sessao, botao-desliga, wifi-watchdog).
5. Conferir no log: `[gate] modelo carregado (onnxruntime, limiar=0.5)` e ~100 ms/frame em CUDA.
6. Rollback: voltar `modelo_chuva_path` para `bestModel.onnx` e reiniciar `citycam`.

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
