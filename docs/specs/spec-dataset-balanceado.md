# SPEC D — Dataset balanceado de intensidade (garoa · moderada · forte)

> **Documento autocontido.** Tudo que é necessário para executar está aqui — não é preciso
> ler a conversa que o originou. Em caso de conflito entre esta spec e o estado real dos
> dados, **pare e reporte a divergência** em vez de improvisar.
>
> Projeto: CityRain (TCC IMT). Convenções do repo: PEP 8, type hints em funções públicas,
> docstrings Google style, nomes de variáveis em inglês, comentários podem ser em português.
> Commits: `tipo: descrição` em português. **Não commitar sem pedido do Rodrigo** — a árvore
> tem trabalho não commitado do J8 (`spec-pipeline-jetson.md`) nos mesmos arquivos.
>
> Escrita em 2026-09-30. **Prazo duro: 20/10/2026.** O escopo de 4 classes não muda.

## Objetivo

Entregar, até **10/10**, um dataset de treino **balanceado** para o modelo de intensidade
(3 classes: `garoa`, `moderada`, `forte`) e três conjuntos de **teste com chuva real**, de
forma que de 11/10 a 16/10 a equipe só precise treinar e avaliar.

O sistema é uma cascata (ver `docs/plano-dataset.md`): o **gate binário** na Jetson decide
chuva/sem chuva e o **modelo de intensidade** no backend decide a classe. `seco` é saída do
gate. Esta spec monta o dataset do modelo de intensidade e, de quebra, reforça o `seco` do
gate.

## Princípio

| Classe | Treino | Teste |
|---|---|---|
| `garoa` | **real**, rótulo de estação (mm/h medido) | real, sessão nunca vista no treino |
| `moderada` | **sintético calibrado** sobre frames reais de garoa | irCNN (pluviômetro) + 23/09 (ordinal) |
| `forte` | **sintético calibrado** sobre frames reais de garoa | irCNN (pluviômetro) + YouTube forte (ordinal) |

**Regras que não se quebram:**

1. **Sintético nunca entra em teste.** Teste é sempre imagem real.
2. **Sintético só nasce de frame da partição de treino.** Base de teste vazaria a cena.
3. **Split por sessão, nunca por frame.** Frames a 1 fps são quase idênticos.
4. **Rótulo real nunca vem do olho.** Vem de estação (mm/h) ou de pluviômetro do dataset
   público. Inspeção visual serve para auditar, não para rotular.

## Estado de partida (verificado em 2026-09-30)

Manifest `ml/data/manifests/manifest_imt.csv` gerado por
`ml/scripts/rotulagem/gerar_manifest.py` com `ml/configs/rotulagem_imt.yaml`:

| Sessão (`evento_id`) | Rótulos | Observação |
|---|---|---|
| `cityrain_frames__2026-08-04` | 493 `seco` | consenso regional; todas as estações zeradas |
| `cityrain_frames2__2026-09-01` | 127 `garoa` | 372 `seco` antigos caíram como `seco_incerto` (fotos mostram chuva) |
| `cityrain_frames3__2026-09-13` | 181 `garoa` | consenso regional, ~1,2 mm/h homogêneo |
| `cityrain_frames4__2026-09-23` | 0 | chuva visível; intensidade entre ~1 e ~10 mm/h, indeterminada |
| `cityrain_frames2__2026-08-07`, `cityrain_frames3__2026-09-05`, `cityrain_frames4__2026-09-16` | 0 | sem GPS; horário confiável |

Regras de rotulagem já implementadas (não refazer): estação ≤ 2 km; fallback de
**consenso regional** (≥ 3 estações com leitura em 5 km, todas na mesma classe);
**confirmação regional do seco** (nenhuma estação em 5 km com chuva em ±60 min). Testes em
`ml/tests/test_rotulagem.py` (142 passando na suíte do `ml`).

Fontes de estação: `ml/data/raw/estacoes/normalizado/cemaden_ped.csv`, baixado por
`ml/scripts/estacoes/baixar_cemaden_ped.py` (credenciais em `ml/.env`). As estações Mooca e
AC Almeida Lima — as mais próximas das rotas — **nunca devolvem dado** no PED.

### O que as outras fotos ensinam sobre a chuva (observado em 30/09)

- **Nossas gotas são pequenas, numerosas e quase em foco** (câmera atrás do para-brisa).
  No RaindropsOnWindshield (`ml/data/raw/public_datasets/raindrops_zenodo/`, 4.593
  máscaras binárias 0/255) as gotas são **manchas grandes e desfocadas** coladas na lente.
  Serve como fonte de *formato* de gota, não de *escala*.
- **Em chuva forte o limpador está ligado** (YouTube 7, 8, 11; nosso 23/09). A densidade
  de gotas no vidro **satura** entre passadas — não cresce sem limite. O que cresce com o
  mm/h é: **névoa/perda de contraste ao longe**, **película d'água** borrando o vidro,
  **spray** de veículos e **poças/espelhamento** no chão.
- **Garoa real também tem limpador e chão molhado** (01/09 07:56, 13/09). Logo,
  chão molhado e limpador **não** separam garoa de forte — o gerador não pode criar esse
  atalho (ver D7).
- Vídeos YouTube de cabine com volante/mãos (`frames10`, `frames12`, `frames15`) e
  noturnos (`frames16`, `frames17`) **não servem** de referência para a nossa câmera.
  `frames11` vai de "just starting to sprinkle" a temporal: progressão ordinal real.

---

# FASE A — Dados reais (01/10 → 05/10)

## D1. Seco sem GPS por consenso metropolitano

### Contexto
O gate precisa de `seco` de mais de uma sessão (hoje é só 04/08). As sessões de 05/09
(142 frames, tarde), 06/08 (103, noite) e 15/09 (22, noite) não têm GPS, mas têm horário.
Se **todas** as estações da lista do script marcaram zero, o carro estava no seco onde quer
que estivesse na RMSP.

### Mudança
1. Baixar CEMADEN de `2026-08-06`, `2026-09-05`, `2026-09-15` (acrescentar a `DIAS_ALVO`).
2. Em `gerar_manifest.py`, novo fallback para frame **sem posição e com timestamp**:
   rótulo `seco` se ≥ 5 estações da série têm leitura em ±60 min e **todas** somam zero.
   `metodo_rotulo = consenso_metropolitano`. Qualquer chuva em qualquer estação → motivo
   `sem_gps_fix` (inalterado). **Nunca** rotula `garoa` sem GPS.
3. Nova coluna `periodo` (`dia`/`noite`, pelo horário local: dia = 06:00–18:30).
4. Flag de config `rotulagem.consenso_metropolitano.ativo` + `--sem-consenso-metropolitano`.

### Aceite
- [ ] Testes novos: todas zeradas → `seco`; uma estação com 0,2 → excluído; < 5 estações →
  excluído; frame com GPS nunca passa por esta regra.
- [ ] `--sem-consenso-metropolitano` reproduz o manifest anterior byte a byte.
- [ ] Relatório imprime quantos `seco` por sessão e por `periodo`.

## D2. Garoa: zona morta avaliada na mediana do consenso

### Contexto
~1.200 frames de 01/09, 13/09 e 23/09 têm **todas** as estações próximas entre 0,6 e
2,4 mm/h — garoa em qualquer estação — mas caem como `sem_consenso_regional` porque uma
estação a 2,4 mm/h está na zona morta do limiar 2,5 (±15%).

### Mudança
No consenso regional, classificar cada estação **sem** zona morta; exigir todas na mesma
classe; aplicar a zona morta **uma vez, sobre a mediana**. A regra da estação próxima não
muda.

### Aceite
- [ ] Teste: estações {1,2; 1,2; 2,4} → `garoa` (mediana 1,2). Estações {2,4; 2,4; 2,6} →
  excluído (classes diferentes). Estações {2,3; 2,4; 2,4} → excluído (mediana na zona morta).
- [ ] Relatório mostra o ganho por sessão. Esperado: `garoa` sobe de 308 para > 1.000.
- [ ] Auditoria visual: grade de 16 frames `garoa` novos por sessão em
  `ml/data/review/garoa_d2/` — todos com chuva visível. Se algum estiver visivelmente seco,
  **parar e reportar**.

## D3. Splits por sessão e manifest de treino

### Mudança
Script `ml/scripts/dataset/montar_splits.py` + `ml/configs/splits_intensidade.yaml`.
Partição **fixa por sessão** (declarada no YAML, não sorteada):

| Partição | Sessões | Uso |
|---|---|---|
| `train` | 01/09 (garoa) até 08:38 local | treino real + bases do sintético |
| `val` | 01/09 a partir de 08:40 local (bloco final, gap de 2 min) | early stopping |
| `test_real` | 13/09 inteira (181 `garoa`) | teste garoa real, sessão nunca vista |
| `test_ordinal_2309` | 23/09 inteira | só ordenação (ver Contrato de saída). Rótulos `garoa` que o D2 der a 23/09 **não** entram em `train`/`test_real`: Vila Prudente (5 km) leu 6–19 mm/h na hora, a classe real é incerta |
| gate `seco` | 04/08 (dia) → train; 06/08 (noite, 103) → test separado por `periodo` | dataset do gate (05/09 e 15/09 tinham chuva na rede: sem `seco`) |

> **Revisado em 30/09** após D1/D2 + regra do zero de báscula: o manifest tem 1.878
> `garoa` (1.697 em 01/09, 181 em 13/09) e 596 `seco` (493 de 04/08 dia, 103 de 06/08
> noite). Dividir 13/09 ao meio deixaria ~90 frames por lado, então 13/09 vira teste
> inteiro e a validação sai do bloco final de 01/09.

Subamostragem: treino com stride de 2 s (`stride_s` no YAML); `val` e `test_real` sem
stride (já são pequenos — reportar métricas por sessão). Saída: `ml/data/splits/intensidade_v1.csv` com colunas
`caminho,classe,mm_h,particao,origem(real|sintetico|irCNN|youtube),evento_id,base_frame,seed`.

### Aceite
- [ ] Nenhum `evento_id` aparece em duas partições (teste automatizado sobre o CSV).
- [ ] Nenhuma linha `sintetico` fora de `train`.
- [ ] Tabela de contagem por (partição × classe × origem) impressa e salva em
  `ml/data/splits/intensidade_v1_resumo.json`.

## D4. irCNN — teste real de moderada/forte

### Contexto
irCNN (Yin et al., 2023): 6 vídeos de chuva com pluviômetro, Hangzhou —
https://doi.org/10.6084/m9.figshare.22122500.v1. É a única fonte acessível com mm/h medido
nas classes altas. Câmera de vigilância (sem para-brisa): o teste mede generalização de
domínio — **reportar como tal**.

### Mudança
1. Baixar para `ml/data/raw/public_datasets/ircnn/`. Ler a licença e o README; registrar
   em `docs/fontes-estacoes.md` (seção nova) URL, licença, resolução temporal do rótulo.
2. Extrair frames a 1 fps → `ml/data/processed/ircnn/`, rótulo mm/h pela série do
   pluviômetro do próprio dataset, mesmas classes e zona morta de 15% do projeto.
3. Manifest `ml/data/manifests/manifest_ircnn.csv`, mesmo schema de colunas do D3.

### Aceite
- [ ] Contagem por classe e por vídeo. **Meta: ≥ 100 frames em `moderada` e em `forte`.**
- [ ] Se o download não existir/for inviável, ou se as classes altas vierem vazias:
  **parar e reportar** com o que foi encontrado (não substituir por outra fonte sem aval).
- [ ] Grade visual de 4 frames por classe em `ml/data/review/ircnn/`.

## D5. YouTube — conjunto ordinal de chuva forte

### Mudança
`ml/data/manifests/manifest_youtube_ordinal.csv` com frames de `processed/youtube/` dos
vídeos de **dashcam externa diurna**: `frames7`, `frames8`, `frames11`, `frames13`,
`frames14` (verificar enquadramento; excluir 10, 12, 15 — cabine — e 16, 17 — noite).
Rótulo **fraco** `>=moderada` (não é classe; é para teste de ordenação). Para `frames11`,
anotar o tempo do vídeo em que a legenda indica a virada para chuva forte e marcar o
trecho anterior como `inicio` e o posterior como `pico`. Até 200 frames por vídeo, stride
uniforme. Excluir frames com texto sobreposto grande.

### Aceite
- [ ] Manifest com `video`, `trecho`, `rotulo_fraco`; grade visual por vídeo em
  `ml/data/review/youtube_ordinal/`.

---

# FASE B — Gerador sintético (01/10 → 10/10)

## D6. Régua: medir a chuva real que temos

### Contexto
O gerador precisa de uma escala ancorada em medida. Temos frames com mm/h medido de ~0,6 a
~2,4 mm/h (garoa) e um teto qualitativo (23/09 e YouTube).

### Mudança
Script `ml/scripts/sintetico/medir_regua.py` que, sobre frames `garoa` de **treino** e
frames secos de 04/08, mede por frame:
- **densidade de gotas no vidro**: blobs pequenos de alta frequência (ex.: diferença de
  gaussianas + limiar), contagem por megapixel e distribuição de raio;
- **contraste ao longe**: contraste RMS da faixa do horizonte (terço superior, excluindo
  céu saturado);
- **nitidez global**: variância do Laplaciano;
- **fração de frames com limpador** (detector simples de faixa escura diagonal, ou
  marcação manual de 50 frames se o detector for ruim — dizer qual foi usado).

Saída: `ml/configs/regua_chuva.json` com média/desvio de cada métrica por faixa de mm/h e
para seco, e as mesmas métricas em 23/09 e nos vídeos YouTube do D5 (referência de
teto). Grade de frames com as gotas detectadas sobrepostas em `ml/data/review/regua/`.

### Aceite
- [ ] Métricas separam seco de garoa (diferença de médias > 1 desvio em pelo menos duas).
- [ ] 23/09 e YouTube forte ficam **além** da garoa em névoa/contraste (se não ficarem,
  reportar — muda a calibração do D7).

## D7. Gerador de chuva calibrado

### Contexto
Bases = frames **reais de garoa da partição `train`** (chão molhado, céu fechado,
limpador já presentes ⇒ nenhum desses vira atalho). O gerador **acrescenta** chuva até a
intensidade-alvo. Ver "O que as outras fotos ensinam" acima: em chuva forte o que cresce é
névoa, película e spray; gota no vidro satura por causa do limpador.

### Mudança
Módulo `ml/src/cityrain_ml/data/sintetico.py` + CLI `ml/scripts/sintetico/gerar.py` +
`ml/configs/sintetico_v1.yaml`. Cada amostra recebe `mm_h_alvo` sorteado em
`moderada ∈ [3,5; 8,5]` ou `forte ∈ [12; 40]` (fora das zonas mortas) e compõe camadas,
todas com parâmetros função de `mm_h_alvo` e da régua do D6:

1. **Gotas no vidro**: densidade ∝ `mm_h_alvo / mm_h_base` × densidade medida na base,
   com **teto de saturação** (fator configurável, inicial 4×) que modela o limpador;
   raio da distribuição medida, cauda maior para forte; aparência = refração (patch do
   fundo invertido e desfocado dentro da gota) + borda escura; formato amostrado das
   máscaras do RaindropsOnWindshield reduzidas à escala medida.
2. **Película d'água**: regiões de desfoque/distorção suave, área ∝ `mm_h_alvo`.
3. **Névoa (atenuação atmosférica)**: modelo de Koschmieder `I = J·t + A·(1−t)`,
   `t = exp(−β·d)`, profundidade `d` aproximada pela linha do horizonte (sem rede de
   profundidade); `β` crescente com `mm_h_alvo` segundo relação empírica de extinção por
   chuva **citada da literatura** (registrar a fonte no docstring) e ajustada para que o
   contraste ao longe caia na faixa observada em 23/09/YouTube (D6).
4. **Riscos (streaks)**: fracos de dia; densidade/comprimento por `mm_h_alvo`
   (Garg & Nayar; Halder et al. 2019).
5. **Spray** atrás de veículos: opcional, desligado por padrão no v1.

Determinístico por `seed`. Gera em `ml/data/synthetic/intensidade_v1/` + manifest com
`base_frame, mm_h_base, mm_h_alvo, classe, seed` e os parâmetros de cada camada.
Meta de volume: **mesmo número de amostras de `moderada` e de `forte` que de `garoa` real
de treino** (ver D3), no máximo 2 sintéticos por base por classe.

### Aceite
- [ ] Testes: mesma seed → mesma imagem (hash); `mm_h_alvo` maior → mais gotas (até o
  teto), menor contraste ao longe, monotonicamente.
- [ ] **Teste de ordenação na própria régua**: aplicar `medir_regua.py` nos sintéticos —
  as métricas de `moderada` ficam entre garoa real e `forte`, e `forte` fica na faixa de
  23/09/YouTube.
- [ ] **Escada visual**: para 12 bases, grade base | moderada | forte em
  `ml/data/review/sintetico_v1/`, mais 23/09 e 2 frames YouTube ao lado como referência.
  **Aprovação visual do Rodrigo antes de gerar o volume final.**

## D8. Seco com asfalto molhado (opcional, se sobrar tempo)

Gerar a partir de frames `seco` de treino uma versão com asfalto escurecido e reflexos,
**rótulo `seco`**, para o gate não aprender "chão molhado ⇒ chuva". Só para o dataset do
gate. Aceite: escada visual aprovada.

---

# Contrato de saída (para o treino, 11/10)

- `ml/data/splits/intensidade_v1.csv` (D3) incluindo sintéticos (D7) com
  `particao=train`, irCNN (D4) com `particao=test_ircnn`, 23/09 (`test_ordinal_2309`) e
  YouTube (`test_ordinal_youtube`).
- Balanceamento: contagens de treino por classe dentro de ±10%; se `garoa` real for maior,
  o loader usa pesos por classe (não descartar dado real).
- Avaliação mínima que o treino deve reportar: F1 macro e matriz de confusão em
  `test_real` + `test_ircnn`; **taxa de ordenação** (fração de pares em que o modelo
  pontua `pico` > `inicio`, 23/09 > garoa de 13/09, YouTube forte > garoa); tudo **com e
  sem sintético** no treino.

# Cronograma e paralelismo

| Bloco | Tarefas | Pode rodar junto com | Prazo |
|---|---|---|---|
| A — rotulagem | D1 → D2 (mesmo arquivo, mesma pessoa/agente) | D4, D5, D6 | 03/10 |
| B — público | D4, D5 | A, D6 | 04/10 |
| C — régua | D6 (usa os 308 `garoa` atuais; refazer após D2) | A, B | 03/10 |
| D — splits | D3 | depois de A | 05/10 |
| E — gerador | D7 (esqueleto já; calibração após D6) | A, B, C | 10/10 |
| F — opcional | D8 | — | se sobrar |
