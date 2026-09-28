# SPEC F1.1 — Histórico de estações pluviométricas para rotulagem

> **Documento autocontido.** Tudo que é necessário para executar está aqui. Em caso de
> bloqueio (cadastro obrigatório, paywall, API fora do ar), **documente o bloqueio e pare**
> — não improvise, não crie contas, não pague nada.
>
> Projeto: CityRain (TCC IMT) — classifica intensidade de chuva a partir de câmera veicular.
> O ground truth vem de pluviômetros públicos: o rótulo de cada frame é derivado da leitura
> em mm/h da estação mais próxima (≤ 2 km) na janela de tempo do frame (±15 min).

## Objetivo

Responder com evidência: **conseguimos leituras históricas de chuva, com boa resolução
temporal, para os dias/horários/locais das nossas três sessões de coleta?**

Esta é a pergunta que destrava (ou redireciona) todo o pipeline de rotulagem. Não é tarefa
de código de produção — é investigação com entregáveis verificáveis.

## As três sessões-alvo (horários LOCAIS, America/Sao_Paulo = UTC−3)

| Data | Janela local | Duração | Bbox GPS da rota (lat / lon) | Contexto visual conhecido |
|---|---|---|---|---|
| **2026-08-04** | 08:12–08:29 | 17 min | −23,5674..−23,5533 / −46,6068..−46,5907 | aparenta seco (amostra conferida) |
| **2026-09-01** | 07:32–08:51 | 80 min | −23,5657..−23,5466 / −46,6593..−46,5880 | **chuva com transição**: gotas fortes 07:32 → para-brisa quase seco 08:11 → gotas esparsas 08:47 |
| **2026-09-13** | 16:31–16:53 | 22 min | −23,5664..−23,5499 / −46,6061..−46,5917 | rua molhada, aparenta garoa/pós-chuva |

Região: centro-sul do município de São Paulo (eixo Cambuci / Vila Mariana / Mooca,
aproximadamente). Buscar cobertura para o dia inteiro de cada data, não só a janela — a
janela de rotulagem é ±15 min, e contexto do dia ajuda na validação.

## Fontes a investigar, nesta ordem

Para cada uma, responder o questionário da seção "Relatório" — mesmo quando a resposta
for "não serve", o porquê documentado tem valor.

1. **CEMADEN** — rede nacional de pluviômetros automáticos, acumulados de **10 min**
   (a melhor resolução candidata). Portal: https://www.gov.br/cemaden/ ; existe portal de
   dados/mapa interativo e um webservice (sws.cemaden.gov.br). Pode exigir cadastro.
2. **CGE-SP** — Centro de Gerenciamento de Emergências da Prefeitura de SP
   (https://www.cgesp.org/). Tem telemétricas próprias na cidade; verificar se o site expõe
   histórico por estação ou apenas condição atual/boletins.
3. **SAISP / DAEE** (https://www.saisp.br/) — rede telemétrica da Grande SP operada pela
   FCTH; historicamente com dados de 10 min. Verificar acesso público ao histórico.
4. **INMET** — API aberta (https://apitempo.inmet.gov.br/, ex.:
   `GET /estacao/{data_ini}/{data_fim}/{codigo}`), estações automáticas com resolução
   **horária**. É o fallback: funciona, mas degrada a janela de rotulagem de ±15 min para
   a hora cheia. Estações candidatas na capital: Mirante de Santana (A701) e Interlagos
   (A771) — ambas longe do bbox; medir a distância real e reportar.

## Regras da investigação

- **Nunca criar conta com dados inventados.** Se uma fonte exigir cadastro, documentar
  exatamente o que pede (URL, campos, prazo de aprovação) e marcar como
  `BLOQUEADO_CADASTRO` — o Rodrigo faz o cadastro depois.
- Não pagar por nada; não aceitar termos de uso em nome de terceiros.
- Respeitar as APIs: sem loops agressivos; salvar cada resposta bruta em disco na primeira
  vez e trabalhar sobre o arquivo salvo.
- Respostas brutas (JSON/CSV/HTML) em `ml/data/raw/estacoes/respostas_brutas/<fonte>/`
  (esse caminho é gitignored — não vai pro git, e é intencional).
- Coordenadas de estação: obter da própria fonte; se vier sem coordenada, procurar no
  catálogo oficial da rede — nunca chutar.

## Entregáveis

### E1 — CSVs normalizados (um por fonte que funcionou)
Em `ml/data/raw/estacoes/normalizado/<fonte>.csv`, schema único:

```
fonte,estacao_id,estacao_nome,lat,lon,ts_utc,acumulado_mm,janela_min
```

- `ts_utc` em ISO 8601 UTC (converter de local quando a fonte publicar em local —
  documentar o fuso assumido).
- `janela_min` = resolução da leitura (10, 60...).
- Cobrir os três dias-alvo por inteiro, todas as estações da fonte num raio de **5 km**
  do centro dos bboxes (5 km na coleta, 2 km será o corte na rotulagem — coletar com folga).

### E2 — Relatório `docs/fontes-estacoes.md`
Estrutura obrigatória, por fonte:

- **Acesso**: URL usada, precisa de cadastro? chave? — passos exatos
- **Resolução temporal** e unidade (mm acumulado por quê janela?)
- **Cobertura histórica**: os 3 dias-alvo estão disponíveis? desde quando há dados?
- **Estações próximas**: tabela `estacao_id, nome, lat, lon, distancia_km_ao_bbox` para as
  ≤ 5 km (distância haversine ao ponto mais próximo do bbox de cada sessão)
- **Amostra real**: 3–5 linhas de dados verdadeiros colados no relatório
- **Veredito**: `VIÁVEL` / `VIÁVEL_COM_RESSALVA` / `BLOQUEADO_CADASTRO` / `INVIÁVEL` + por quê

E ao final, a **recomendação única**: qual fonte alimenta o pipeline de rotulagem, e qual
é o plano B.

### E3 — Validação de coerência (a parte mais importante)
Com os dados obtidos, para cada sessão plotar/tabular `acumulado × tempo` da estação mais
próxima e confrontar com o contexto visual da tabela de sessões:

- **01/09, 07:32–08:51**: a estação **tem que registrar chuva > 0** em parte da janela, com
  tendência decrescente (chovia forte no início, quase parou no meio). Se todas as estações
  próximas derem zero o dia todo, isso é um resultado importante — significa que o
  alinhamento espaço-temporal tem problema (estação longe demais? chuva muito localizada?
  fuso errado na conversão?). Reportar como `INCOERENTE`, com os dados, sem maquiar.
- **04/08, manhã**: esperado ~0 mm na janela.
- **13/09, ~16:30**: esperado chuva fraca na janela ou nas horas imediatamente anteriores
  (rua molhada).

Resultado em uma seção "Validação de coerência" do relatório: uma tabela por sessão com
`hora, mm` da estação escolhida + veredito `COERENTE` / `INCOERENTE` / `INCONCLUSIVO`.

## Fora de escopo (não fazer)

- Não implementar o cliente de ingestão do backend (isso é outra tarefa, F1.2).
- Não rotular nenhum frame.
- Não commitar CSVs de dados sob `ml/data/` (gitignored de propósito). O que vai pro git é
  só o relatório `docs/fontes-estacoes.md` e eventuais scripts auxiliares de download
  (coloque-os em `ml/scripts/estacoes/`, com type hints e docstrings).

## Critérios de aceite (todos obrigatórios)

- [ ] As 4 fontes investigadas e documentadas no relatório, cada uma com veredito e evidência
      (URL + amostra real ou descrição exata do bloqueio)
- [ ] ≥ 1 fonte com status `VIÁVEL` ou `VIÁVEL_COM_RESSALVA` **com CSV normalizado cobrindo
      os 3 dias-alvo** — OU, se nenhuma for viável sem cadastro, todos os bloqueios
      documentados com passo a passo de cadastro pro Rodrigo executar
- [ ] Tabela de estações ≤ 5 km com coordenadas reais (fonte oficial) e distância haversine
      calculada — nenhuma coordenada inventada
- [ ] Validação de coerência feita para as 3 sessões, com veredito honesto (`INCOERENTE`
      é resultado aceitável; dado maquiado não é)
- [ ] Todos os `ts_utc` do CSV realmente em UTC (verificação: a chuva de 01/09 deve aparecer
      entre 10:32 e 11:51 **UTC**)
- [ ] `git status` limpo em `ml/data/`; relatório e scripts commitados
- [ ] Recomendação final única e acionável: fonte principal + plano B + o que degrada
      (ex.: "INMET horário ⇒ janela de rotulagem vira a hora cheia; impacto: X")

## Verificação rápida (para quem revisar)

```bash
head -3 ml/data/raw/estacoes/normalizado/*.csv         # schema confere?
grep -c "2026-09-01" ml/data/raw/estacoes/normalizado/*.csv   # tem o dia-chave?
git status --porcelain ml/data/ | wc -l                 # esperado: 0
```
