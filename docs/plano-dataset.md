# Plano de Dataset & Baselines — CityRain

> Plano operacional criado em 2026-09-15 a partir do inventário (`docs/acervo-dados.md`, 05/09)
> e da auditoria das quatro pastas de coleta feita em 15/09 (contagens, GPS, sessões e
> orientação verificados frame a frame). Janela: **5 semanas** (15/09 → 17/10), com coleta
> de outubro contínua por cima.
>
> Versão visual para compartilhar: artifact "Plano de Dataset CityRain" (link com o Rodrigo).

## Princípio organizador

A arquitetura em cascata resolve a divergência binário × 4 classes do inventário:

```
[Jetson] gate BINÁRIO chuva/sem_chuva  →  [Backend] 3 CLASSES garoa/moderada/forte  →  [Dashboard]
         só frames com chuva sobem            roda na ingestão                           4 classes ponta a ponta
```

Cada estágio tem seu dataset, com ground truth próprio:

| | Dataset A — gate binário | Dataset B — 3 classes |
|---|---|---|
| Ground truth | rótulo visual (revisão humana) | mm/h da estação ≤ 2 km, janela ±15 min |
| Fontes | 14.151 pré-rotulados + `framesSemNada` + públicos | sessões com GPS (04/08, 01/09, 13/09) + coleta out |
| Bloqueio atual | revisão humana parada | **rotulagem feita (18/09), mas só 478 frames e só `garoa`** — ver F1.3 |

**Regra anti-skew:** o 3-classes é servido atrás do gate ⇒ treina só em frames que o gate
deixaria passar. Rodar o gate sobre o Dataset B antes de treinar é parte do pipeline.

## Limiares (fase 3-classes)

Báscula CGE = 0,2 mm por tombo em janela de 10 min ⇒ degrau mínimo de **1,2 mm/h**.
(Confirmado em 18/09 na fonte que estamos de fato usando: a báscula CEMADEN é de
**0,19634 mm/tombo** ⇒ degrau de 1,178 mm/h — mesma ordem, o degrau de 1,2 mm/h vale.
A API reporta 1 tombo arredondado como `0.2`; ≥ 2 tombos vêm com precisão cheia.)
Cortes ancorados na escala AMS; desviam do INMET (forte > 25 mm/h) de propósito — com 25 a
classe `forte` ficaria vazia até novembro. **Documentar o desvio no TCC.**

| Classe | mm/h | Decidida por |
|---|---|---|
| `seco` | 0 | gate (Jetson) |
| `garoa` | 0 < i ≤ 2,5 | backend |
| `moderada` | 2,5 < i ≤ 10 | backend |
| `forte` | > 10 | backend |

Regras de rotulagem: janela **centrada ±15 min** · **zona morta de 15%** em torno de cada
limiar (frame na fronteira é descartado) · **raio máximo 2 km** frame ↔ estação.

---

## F0 — Higiene e fundações (15–19/09)

### F0.1 Normalizar orientação por pasta — *Rodrigo*
Script `ml/scripts/preprocessamento/normalizar_orientacao.py`. Rotaciona 180° **somente**
`cityrain_frames`, `cityrain_frames2`, `cityrain_frames3`; a `framesSemNada` já está correta
(verificado visualmente em 15/09). Saída em `ml/data/processed/imt_coleta/`; `raw/` intocado.
Remove os 65 jpg de 0 byte e o json órfão `frame_20260905_151154_299.json`.

**Aceite:**
- [ ] `processed/imt_coleta/` contém as 4 pastas; amostra visual de cada uma confere (capô embaixo, céu em cima)
- [ ] zero arquivos de 0 byte na saída; contagens batem: 1.017 + 4.746 + 1.385 + 4.783
- [ ] rodar o script duas vezes não re-rotaciona (idempotente)
- [ ] script commitado; pixels não (`git status` limpo em `ml/data/`)

### F0.2 Hora do GPS (RMC) no JSON de captura — *Rodrigo* · **pré-requisito p/ coleta nova**
`capturado_em_utc` vem só do relógio do sistema (Jetson sem RTC — uma fonte só). Alterar
`captura.py`/`gps.py` para gravar também a hora da sentença RMC em campo separado
(ex.: `gps.hora_rmc_utc`). Duas fontes independentes = timestamp auditável.

**Aceite:**
- [ ] JSON novo tem `hora_rmc_utc` preenchido quando há fix; `null` sem fix
- [ ] teste de bancada: |hora sistema − hora RMC| < 2 s com NTP ok
- [ ] deploy feito na Jetson (não só no repo) antes da primeira saída de outubro

### F0.3 Rebaixar YouTube em 1080p — *Paulo* (paralelo, não bloqueia)
Trocar o filtro do yt-dlp em `captura_frames.py` para
`-f "bv*[height<=1080]+ba/b[height<=1080]/b" --merge-output-format mp4` e re-rodar.
Atenção: `baixar_video()` pula destino existente — forçar re-download.

**Aceite:**
- [ ] ≥ 90% dos vídeos re-baixados em ≥ 720p (alguns podem não ter faixa melhor)
- [ ] `manifest.csv` regenerado com as novas resoluções

### F0.4 Atualizar `docs/acervo-dados.md` — *Rodrigo*
Incluir: `cityrain_frames3` (2 sessões, 1.385 frames), a descoberta de que `framesSemNada`
contém chuva noturna (nome engana), a cascata como decisão, os limiares acima.

**Aceite:**
- [ ] doc commitado; seção "Divergência de escopo" reescrita como resolvida pela cascata

---

## F1 — Ground truth de estação (15–26/09) · **caminho crítico**

> **ATUALIZAÇÃO 16/09/2026 — F1.1 CONCLUÍDA.** Cadastro no PED feito, API oficial
> do CEMADEN acessada, **1.281 leituras em resolução de 10 min** baixadas para os
> 3 dias-alvo, e a validação de coerência passou nas 3 sessões. O maior risco do
> plano caiu. Detalhes e pegadinhas de acesso: `docs/fontes-estacoes.md` (adendo
> no fim). Script: `ml/scripts/estacoes/baixar_cemaden_ped.py`.
>
> **ATUALIZAÇÃO 18/09/2026 — ressalva fechada + download completo.** A coluna
> `valor` **é incremento de precipitação do intervalo de 10 min** (`mm_h = valor * 6`),
> confirmado por duas evidências independentes: quantização em múltiplos exatos de
> 0,19634 mm (resolução de tombo da báscula) e reprodução da série horária pública
> pela **soma** dos incrementos (MAE 0,070 mm). Não é acumulado móvel.
> `cemaden_ped.csv` foi de 1.281 para **1.642 leituras** (33 de 45 pares).
>
> ⚠️ **Os 12 pares restantes não existem** — a API responde 202 "Nenhum resultado"
> para Mooca, AC Almeida Lima, Vila Formosa e Vila Maria nos 3 dias. **Mooca e AC
> Almeida Lima eram as duas estações a ~0 km das rotas e estão fora do jogo**;
> F1.3 tem de recalcular distâncias sobre as 11 estações que reportam.
> Detalhes: `docs/fontes-estacoes.md` (Adendo 2).

### F1.1 Confirmar acesso a histórico de chuva — *Gabriel + Rodrigo* · **maior risco do plano**
Precisamos das leituras de **04/08, 01/09 e 13/09** para estações no centro-sul de SP
(bbox lat −23,55..−23,57 / lon −46,59..−46,66). Ordem de tentativa:
1. **CEMADEN** — acumulado 10 min, exige cadastro no portal de dados
2. **CGE-SP** — telemétricas; verificar se expõe histórico ou só tempo real
3. **INMET** — API aberta porém horária (degrada a janela; fallback)

**Aceite:**
- [ ] CSV com leituras reais dos 3 dias, de ≥ 1 estação a ≤ 2 km de algum trecho das rotas
- [ ] resolução temporal documentada (10 min? horária?) — define a janela real de rotulagem
- [ ] se nenhuma fonte cobrir os 3 dias: decisão de fallback registrada neste arquivo

### F1.2 Cliente de ingestão + tabela de leituras — *Gabriel*
`backend/app/ingestion/` está vazio. Implementar cliente da fonte escolhida + model/tabela
de leituras de estação (estação, ts, acumulado, fonte). Alinhar também o
`MUDANCAS_NECESSARIAS_BACKEND.md`: o `ml_service.py` atual assume que a borda classifica;
na cascata o backend classifica **no fluxo de ingestão**.

**Aceite:**
- [ ] job de ingestão roda e persiste leituras no Postgres (tempo real e/ou backfill histórico)
- [ ] leituras dos 3 dias de teste carregadas no banco
- [ ] resposta do Gabriel sobre a mudança do fluxo de classificação registrada

### F1.3 Script de rotulagem → `manifest.csv` — *Rodrigo*
`ml/scripts/rotulagem/gerar_manifest.py`: para cada frame com GPS fix, acha a estação
≤ 2 km, agrega a janela ±15 min, aplica limiares + zona morta e emite
`arquivo, ts_utc, lat, lon, estacao_id, dist_m, mm_h, classe, evento_id`.
Manifest e script **vão pro git**; pixels não.

**Aceite:**
- [x] `manifest.csv` gerado para as 3 sessões com GPS → `ml/data/manifests/manifest_imt.csv`
- [x] colunas completas; frames sem fix ou > 2 km saem com motivo de exclusão em coluna própria
- [x] reproduzível: mesmo input ⇒ mesmo output (verificado por sha256 em duas execuções; 39 testes em `ml/tests/test_rotulagem.py`)

> **RESULTADO 18/09/2026 — F1.3 implementada, e o número é ruim.** Script em
> `ml/scripts/rotulagem/gerar_manifest.py`, config em `ml/configs/rotulagem_imt.yaml`.
> Dos 7.148 frames com metadados, **apenas 478 foram rotulados** (351 `seco` +
> 127 `garoa`); **zero `moderada`, zero `forte`**.
>
> | motivo de exclusão | frames |
> |---|---|
> | `sem_estacao_no_raio` (> 2 km) | 4.810 |
> | `sem_gps_fix` | 1.703 |
> | `sem_leitura_na_janela` | 157 |
>
> **Só a sessão de 01/09 sobrevive.** Com Mooca e AC Almeida Lima sem dado, a
> estação mais próxima das rotas de 04/08 e 13/09 é o Ipiranga a 2,18 km e 2,29 km
> — acima do raio de 2 km, então as duas sessões saem inteiras do dataset. Em 01/09
> a rota passa a 0,37 km da AC Central de SP e 0,62 km do Centro, que ancoram os
> 478 rótulos.
>
> **Afrouxar o raio não cria as classes que faltam:**
>
> | raio | seco | garoa | moderada | forte | total |
> |---|---|---|---|---|---|
> | 2 km | 351 | 127 | 0 | 0 | 478 |
> | 3 km | 1.241 | 1.088 | 0 | 0 | 2.329 |
> | 5 km | 2.272 | 1.790 | 0 | 0 | 4.062 |
>
> As 4 leituras `moderada` de 01/09 são de Vila Prudente (3,55 km) e Ipiranga
> (2,37 km), mas a regra escolhe a estação **mais próxima** com leitura na janela —
> e a mais próxima registrou garoa. Afrouxar o raio só multiplica `seco`/`garoa`.
>
> ⚠️ **Consequência para F3.2:** não há Dataset B de 3 classes com a coleta atual —
> há um dataset de 1 classe (`garoa`). O baseline 3-classes fica **bloqueado até a
> coleta de outubro (F4)**, e a prioridade de F4 sobe de "importante" para
> **pré-requisito**. O que dá para fazer já: o gate binário (F3.1), que usa o
> Dataset A e não depende disso.
>
> **Ações que destravariam mais dados:**
> 1. **GPS**: 1.703 frames (24%) perdidos por falta de fix, 917 deles em 01/09 —
>    a maior perda de dado evitável. Reforça F0.2.
> 2. Planejar as rotas de outubro para passar a ≤ 2 km de uma estação **que
>    reporta** (as 11 confirmadas), não das mais próximas no mapa.

### F1.4 Sanity check de ouro: sessão de 01/09 — *Gabriel*
A sessão tem transição visual documentada: gotas fortes 07:32 → para-brisa quase seco 08:11
→ gotas esparsas 08:47. O rótulo derivado da estação **tem que reproduzir essa curva**.

**Aceite:**
- [ ] plot mm/h da estação × tempo sobreposto aos 3 marcos visuais; transição bate (chuva no início, seca no meio, respingos no fim)
- [ ] se não bater: investigação de causa (distância? janela? estação errada?) antes de qualquer treino

---

## F2 — Montagem dos datasets (22/09–03/10)

### F2.1 Dataset A: fechar a revisão humana — *equipe toda*
1.975 frames de alta confiança + 100 duvidosos, com o rotulador que já existe em
`code/classificador/`. 4 pessoas × ~500 frames = uma tarde.

**Aceite:**
- [ ] 100% dos 2.075 revisados; taxa de correção sobre o Haiku registrada (vira evidência metodológica)
- [ ] `dataset_bruto/{chuva,sem_chuva}` consolidado

### F2.2 Dataset A: incorporar `framesSemNada` — *Gabriel*
Contém chuva noturna pesada + garagem — cenário difícil do gate. Rotular visualmente por
blocos de sessão (relógio de maio não permite estação).

**Aceite:**
- [ ] 4.783 frames legíveis rotulados chuva/sem_chuva por bloco
- [ ] blocos noturnos com chuva presentes no split de treino **e** teste do gate

### F2.3 Split por evento com pHash — *Rodrigo*
70/15/15 **por evento/sessão, nunca por frame**. pHash contra vazamento (passo 06 do
classificador, já desenhado). `frames16` (58% do público) nunca cruza splits.

**Aceite:**
- [ ] nenhum evento/vídeo aparece em mais de um split (verificação automática no script)
- [ ] pares pHash-próximos entre splits = 0
- [ ] estatísticas por classe e por split commitadas junto do split

### F2.4 Dataset B: filtrar pelo gate — *Rodrigo*
Rodar o gate atual sobre os frames rotulados do manifest; o 3-classes treina só no que passa.

**Medido em 18/09 nas janelas reais de sessão (±30 min):** `forte` de fato fica
vazia até outubro — o pico de 37,8 mm/h de 01/09 (Vila Prudente) ocorre às 06:20 UTC,
horas antes da sessão que começa 10:32 UTC. Já `moderada` **não** está vazia:
4 leituras a 3,5 mm/h dentro da janela de 01/09 (Vila Prudente, Ipiranga). Quantos
frames caem a ≤ 2 km dessas estações nesses minutos é o que F1.3 responde.

**Aceite:**
- [ ] manifest ganha coluna `passou_gate` (com versão/limiar do gate usados)
- [ ] contagem por classe pós-gate documentada; taxa de descarte do gate sobre frames *com* chuva reportada (se alta, é sinal de recall ruim do gate — alimenta F3.1)

---

## F3 — Baselines de modelo (29/09–17/10)

### F3.1 Gate: re-treinar MobileNetV2 — *Rodrigo + Guilherme*
Arquitetura já roda embarcada (`ml/scripts/captura/modelo_chuva/`). Re-treinar com Dataset A.
Baixar `limiar_chuva` 0,5 → 0,3 (falso positivo custa banda; falso negativo custa alerta).

**Aceite:**
- [ ] recall de chuva ≥ 0,95 no teste (split por evento)
- [ ] export ONNX validado na Jetson: latência por frame e FPS medidos e registrados
- [ ] novo limiar configurado via `cityrain_config.json` (não hardcoded)

### F3.2 Backend 3-classes: comparação de candidatos — *Rodrigo + Guilherme*
Candidatos (nenhum fechado): MobileNetV3-Large, ResNet18, EfficientNet-B0, todos ImageNet.
Estratégia p/ pouco dado: estágio 1 pré-treino binário/públicos, estágio 2 fine-tune 3 classes.
Temporais (CNN+GRU) ficam para depois do primeiro baseline.

**Aceite:**
- [ ] 1 YAML por experimento em `ml/configs/`; cada um reproduzível do zero
- [ ] tabela comparativa (F1 macro, recall por classe, matriz de confusão) em `docs/`
- [ ] mesmo split e mesma seed para todos os candidatos (comparação justa)

### F3.3 Infra mínima de treino — *Rodrigo + Guilherme*
`ml/src/cityrain_ml/`: loader que lê o manifest, loop de treino com seed fixa, log CSV por época.

**Aceite:**
- [ ] `python -m cityrain_ml.train --config ml/configs/<exp>.yaml` roda ponta a ponta
- [ ] duas execuções com a mesma config produzem métricas iguais (±ruído de GPU documentado)

---

## F4 — Coleta de outubro (contínua, oportunista)

Meta: **8–12 sessões chuvosas distintas**, 30–60 min, variando horário/trajeto/intensidade.
Prioridade absoluta: sair quando o CGE indicar **moderada/forte** — única forma de popular as
classes vazias.

> **Elevado a pré-requisito em 18/09** (não é mais só "importante"): F1.3 mostrou que a
> coleta atual rende **zero** frames `moderada`/`forte` em qualquer raio testado. Sem F4
> não existe Dataset B de 3 classes, e F3.2 não tem o que treinar. Ao escolher o trajeto,
> conferir que ele passa a ≤ 2 km de uma das **11 estações que efetivamente reportam** —
> Mooca e AC Almeida Lima são as mais próximas no mapa e não servem. Manter 1 fps (redundância se resolve subamostrando no treino; preserva a
opção de modelos temporais).

**Checklist pré-saída (imprimir/fixar):**
1. NTP sincronizado + `hora_rmc_utc` aparecendo no JSON (F0.2 deployado)
2. GPS com fix antes de partir
3. Câmera montada na orientação correta — conferir um frame no local
4. Trajeto passa a ≤ 2 km de uma estação escolhida **antes** de sair

**Pós-sessão (mesmo dia):** rodar `gerar_manifest.py` → commitar manifest da sessão.

**Aceite da fase:**
- [ ] ≥ 8 eventos novos rotulados
- [ ] ≥ 2 eventos contendo `moderada` ou `forte`
- [ ] zero sessões com timestamp inauditável (RMC ausente com fix disponível)

---

## Riscos e fallbacks

| Risco | Impacto | Mitigação |
|---|---|---|
| ~~Histórico de estação inacessível (F1.1)~~ | **resolvido 16/09** | CEMADEN/PED entregou 10 min para os 3 dias-alvo; coerência validada nas 3 sessões |
| ~~Semântica do `valor` incerta (bloqueava F1.3)~~ | **resolvido 18/09** | incremento de 10 min, `mm_h = valor * 6`; confirmado por quantização (0,19634 mm/tombo) e por soma vs. série horária pública |
| Estações a 0 km das rotas sem dado nenhum | **alto, novo 18/09** | Mooca e AC Almeida Lima respondem 202 nos 3 dias; F1.3 usa só as 11 que reportam, e a distância média frame↔estação sobe |
| Não chover forte até novembro | alto | já embutido: binário + garoa/moderada é a entrega defensável; `forte` é condicional e dito como tal |
| Gate descartar chuva fraca na borda | médio | limiar 0,3 + auditar a `pasta_sem_chuva_pendente` que a Jetson guarda localmente |
| Backend na contramão da cascata | médio | alinhar via `MUDANCAS_NECESSARIAS_BACKEND.md` ainda em F1 |
| Vazamento no split (`frames16` = 58% do público) | médio | split por evento/vídeo + pHash; verificação automática em F2.3 |
| Dataset B tem só 1 classe (`garoa`) após F1.3 | **alto, novo 18/09** | F3.2 bloqueado até F4; coleta de outubro passa a pré-requisito, com trajeto planejado por estação que reporta |
| 24% dos frames perdidos por falta de GPS fix | **médio, medido 18/09** | 1.703 frames, 917 só em 01/09 — reforça F0.2 (hora RMC) e checklist de fix antes de partir |

## O que vai pro git

- **Vai:** scripts (normalização, rotulagem, treino), `manifest.csv`, configs YAML, tabela de resultados, este plano.
- **Não vai:** pixels (`ml/data/raw/**`, `processed/**` — ignorados), pesos (`checkpoints/` — exportar ONNX pro backend por outro canal).
