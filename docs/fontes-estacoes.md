# Fontes de dados históricos de estações pluviométricas — investigação F1.1

> Executa a spec `docs/specs/spec-historico-estacoes.md`. Investigação realizada em
> 15/09/2026. Todas as respostas brutas usadas aqui estão salvas em
> `ml/data/raw/estacoes/respostas_brutas/<fonte>/` (gitignored). Os CSVs normalizados
> estão em `ml/data/raw/estacoes/normalizado/` (gitignored). Nenhuma coordenada ou
> leitura abaixo foi inventada — toda coordenada vem de um catálogo oficial citado, e
> todo valor numérico foi de fato obtido de uma resposta HTTP salva em disco.

## Resumo executivo

Das 4 fontes, **nenhuma** dá acesso público, sem cadastro e sem captcha, a dados
históricos de precipitação fina (10 min) para os 3 dias-alvo com a latência que a
coleta exige. O quadro real é mais nuançado que "bloqueado" vs. "livre":

| Fonte | Veredito | Cobre 04/08 | Cobre 01/09 | Cobre 13/09 |
|---|---|---|---|---|
| CEMADEN | `VIÁVEL_COM_RESSALVA` (via endpoint não documentado) / `BLOQUEADO_CADASTRO` (via API oficial) | Não (fora da janela de 360h) | Sim (qualitativo) | Sim (qualitativo) |
| CGE-SP | `VIÁVEL_COM_RESSALVA` (resolução diária, sem coordenadas) | Sim | Não (mês não publicado) | Não (mês não publicado) |
| SAISP/DAEE | `INVIÁVEL` | Não | Não | Não |
| INMET | `VIÁVEL_COM_RESSALVA` (ZIP anual) / bloqueado por reCAPTCHA (API "oficial" documentada) | Sim | Não (mês não publicado) | Não (mês não publicado) |

**Nenhuma fonte cobre os 3 dias-alvo simultaneamente sem cadastro.** O motivo
dominante não é bloqueio de acesso — é **atraso de publicação**: em 15/09/2026, os
dois provedores com arquivo público mensal/anual (CGE-SP, INMET) só tinham dados
publicados até 31/08/2026. O CEMADEN tem um caminho não-documentado que cobre os
últimos ~15 dias (logo alcança 01/09 e 13/09, mas não 04/08). Ver seção
"Recomendação final".

---

## 1. CEMADEN

### Acesso

Duas vias completamente diferentes foram encontradas:

**Via A — API oficial "PED" (Plataforma de Entrega de Dados)**
- Documentação Swagger pública, sem login: `https://sws.cemaden.gov.br/PED/api/ui/`
  (spec JSON salvo em `respostas_brutas/cemaden/ped_swagger3.json`).
- Endpoints relevantes: `GET /pcds-acum/acumulados-historicos` (acumulados 1h/3h/…/120h
  por estação e data de referência), `GET /pcds-cadastro/estacoes`,
  `GET /pcds-cadastro/dados-cadastrais`, `GET /pcds/dados_pcd` (dado ambiental bruto,
  até 30 dias por chamada).
- **Todos exigem header `token` (JWT), obtido em `POST` a `/controle-token/tokens`.**
  Esse token só é emitido após cadastro de usuário em
  `https://ped.cemaden.gov.br/cadastrarUsuario` — front-end Vue, engenharia reversa do
  bundle (`ped_app.js`) confirma os campos: **Nome**, **E-mail (\*)**, **Senha (\*)**.
  O fluxo parece ser autoatendimento (cria a conta e já libera login,
  `"Usuário {email} cadastrado com sucesso!" → redireciona para /efetuarLogin`) — não
  há evidência de aprovação manual com prazo, mas isso não foi testado (não criamos
  conta, por regra). **Veredito desta via: `BLOQUEADO_CADASTRO`.**

**Via B — backend JSON do Mapa Interativo (não documentado)**
- Descoberto por engenharia reversa do JS público do
  `https://mapainterativo.cemaden.gov.br/` (`script.js`, `grafico_pcds.php`).
- Endpoint: `GET https://mapservices.cemaden.gov.br/MapaInterativoWS/resources/horario/<idEstacao>/<horas>`
  — **sem autenticação, sem captcha**, `horas` até ~360 (≈15 dias) testado com sucesso.
- Retorna JSON com `estacao` (inclui `latitude`/`longitude` oficiais), `datas`,
  `horarios` e `acumulados` (matriz dia × hora).
- **Fuso confirmado empiricamente como UTC**: no momento da coleta (2026-09-16
  02:36 UTC), o último valor não-nulo do dia corrente aparecia na hora rotulada
  `"2h"` — compatível só se os rótulos forem UTC (se fossem locais, `"2h"` local
  seria no futuro). Ver `respostas_brutas/cemaden/horario_3179_360.json`.
- **Ressalva importante**: a semântica exata do campo `acumulados` não é
  documentada. Os valores sobem, platôam e decaem ao longo de várias horas — um
  padrão compatível com algum tipo de "acumulado corrente" (ex.: acumulado móvel de
  24h recalculado a cada hora), **não** com um delta limpo de chuva da própria hora.
  Por isso os valores desta via foram usados só como indício qualitativo na
  validação de coerência (seção 5), e não entraram no CSV com a mesma confiança que
  um `acc1hr` documentado teria.
- Janela de disponibilidade: consultado em 15/09/2026, cobre aproximadamente
  01/09/2026 até 16/09/2026 — **não alcança 04/08/2026**.
- **Veredito desta via: `VIÁVEL_COM_RESSALVA`.**

### Resolução temporal

- Via A (oficial): 10 min é a resolução nativa dos pluviômetros CEMADEN (conforme a
  própria spec e a documentação Swagger, que também expõe acumulados de 1h/3h/…/120h).
  Não pôde ser confirmada com uma amostra real por causa do bloqueio de cadastro.
- Via B: 1 leitura por hora (confirmado empiricamente), de semântica de acumulação
  não confirmada (ver acima).

### Cobertura histórica

- Via A: catálogo indica dados desde a instalação de cada estação (anos, conforme
  campo `data_instalacao` no exemplo do Swagger — não verificado com dado real).
- Via B: janela móvel de ~15 dias a partir da data da consulta. Em 15/09/2026,
  alcança 01/09 e 13/09, não alcança 04/08.

### Estações próximas (≤ 5 km, coordenadas do feed oficial `resources.cemaden.gov.br/dados/311_24.json`)

| codestacao | nome | lat | lon | dist (km) |
|---|---|---|---|---|
| 355030826A | Mooca | -23.547 | -46.596 | 0.00 |
| 355030831A | AC Almeida Lima | -23.55196 | -46.60861 | 0.00 |
| 355030833A | AC Central de SP | -23.54331 | -46.63599 | 0.37 |
| 355030857A | Centro | -23.541 | -46.629 | 0.62 |
| 355030812A | Luz | -23.53102 | -46.63253 | 1.73 |
| 355030871A | Ipiranga | -23.587 | -46.602 | 2.18 |
| 355030877A | Vila Formosa | -23.561 | -46.564 | 2.45 |
| 355030869A | Vila Prudente | -23.584 | -46.561 | 3.42 |
| 355030808A | Vila Clementino | -23.599 | -46.65 | 3.70 |
| 355030860A | Limão | -23.511 | -46.667 | 4.04 |
| 355030853A | Pinheiros | -23.563 | -46.703 | 4.45 |
| 355030878A | Lapa | -23.522 | -46.695 | 4.55 |
| 355030811A | AC Santana | -23.50248 | -46.62884 | 4.91 |
| 355030854A | Vila Maria | -23.502 | -46.591 | 4.96 |
| 354880701A (São Caetano do Sul) | Centro | -23.609 | -46.573 | 4.96 |

Distância = haversine ao ponto mais próximo dentre os 3 bboxes das sessões
(fórmula em `ml/scripts/estacoes/distancia.py`). Densidade excelente: 4 estações a
menos de 1 km de alguma sessão.

### Amostra real

Da Via B, estação Ipiranga (355030871A / idEstacao 3614, 2.18 km), dia 01/09/2026,
horas em UTC (arquivo `horario_3614_360.json`):

```
09h UTC  acumulado=2.55242 mm
10h UTC  acumulado=2.55242 mm
11h UTC  acumulado=2.55242 mm   <- dentro da janela da sessão (10:32-11:51 UTC)
12h UTC  acumulado=2.35608 mm
```

Estação AC Central de SP (idEstacao 3179, 0.37 km), dia 13/09/2026:

```
18h UTC  acumulado=1.0 mm
19h UTC  acumulado=0.8 mm   <- dentro da janela da sessão (19:31-19:53 UTC)
20h UTC  acumulado=0.6 mm
```

### Veredito

**`VIÁVEL_COM_RESSALVA`** — real e sem custo, mas com duas vias distintas e nenhuma
delas ideal: a API oficial (10 min, semântica limpa) está atrás de cadastro; a via
sem login tem semântica de acumulação não confirmada e janela de só ~15 dias. Maior
densidade de estações próximas entre as 4 fontes (15 estações ≤ 5 km, 4 delas
< 1 km).

---

## 2. CGE-SP

### Acesso

- Site: `https://www.cgesp.org/v3/`. **Sem cadastro, sem chave, sem captcha** para
  tudo que foi acessado.
- Lista de estações telemétricas (nomes de bairro, sem coordenadas):
  `https://www.cgesp.org/v3/estacoes-meteorologicas.jsp` → links
  `estacao.jsp?POSTO=<id>`. Confirmamos POSTOs relevantes à região: Vila Mariana=495,
  Móoca=1000860, Ipiranga=1000840, Sé=503, Vila Prudente=524, Jabaquara=634.
- Cada `estacao.jsp?POSTO=<id>` mostra só o estado atual + "histórico das últimas
  24h" (dado horário real, mas **não navegável para datas passadas** — testamos
  parâmetros `NDIAS`, `DATAINI/DATAFIM`, `DIAS` no iframe interno
  (`processo_cge.jsp`) e todos foram ignorados, sempre retornando a mesma janela
  fixa de 24h a partir de "agora"; ver `respostas_brutas/cgesp/processo_cge_495_ref.html`).
- **Achado técnico relevante**: acessar `processo_cge.jsp` direto dá **403** ("Não é
  permitido acesso direto... Acesse a partir de https://www.saisp.br/"). Só funciona
  enviando `Referer: https://www.saisp.br/`. Isso confirma que CGE-SP e SAISP
  compartilham o mesmo backend de telemetria (operado pela FCTH) — não são fontes
  independentes.
- **Arquivo histórico real, sem login**: a CGE-SP publica um boletim mensal em XLSX
  num compartilhamento Nextcloud público operado pela SAISP:
  `https://arquivos.saisp.br/nextcloud/index.php/s/qikdinFyAM33MJK?path=%2FBOLETIM_PLUVIOMETRICO`.
  Acessamos via WebDAV público (`PROPFIND`/`GET` em
  `.../nextcloud/public.php/webdav/BOLETIM_PLUVIOMETRICO/<ano>/`), sem qualquer
  autenticação além do token do link. Estrutura por ano, arquivo
  `<ano>-<mes>-PLUVIOMETRIA-CGESP.xlsx`, indo de 2010 até o mês corrente.
  **Em 15/09/2026, o último arquivo disponível era `2026-08-...xlsx` — setembro
  ainda não publicado** (atraso de publicação de pelo menos 2 semanas).

### Resolução temporal

- Página ao vivo (`estacao.jsp`): horária, mas só últimas 24h.
- Boletim XLSX: **total diário** por estação (uma coluna por dia do mês). Não dá
  para isolar a janela de ±15 min de uma sessão — é o total do dia inteiro.

### Cobertura histórica

- Boletim XLSX cobre 2010–08/2026 (mês corrente sempre ausente até ser publicado).
- 04/08/2026: **coberto** (mês de agosto já publicado).
- 01/09/2026 e 13/09/2026: **não cobertos** (setembro não publicado em 15/09/2026).

### Estações próximas

**Não foi possível montar uma tabela de coordenadas para CGE-SP.** O site expõe só
um mapa-imagem estático com um `<map>` de pixels (sem lat/lon) em
`mapas.jsp?arq=estacoes`; não há KML/XML/JSON público de coordenadas (tentativas em
`/v3/xml/estacoes.xml` e variantes retornaram bloqueio de WAF, não um recurso
existente). As estações mais próximas por **nome de bairro** (evidência textual, não
geométrica) são Vila Mariana, Móoca, Ipiranga, Sé, Vila Prudente e Jabaquara — mas
sem coordenada oficial da própria CGE-SP, essas linhas ficam com `lat`/`lon` vazios
no CSV normalizado (nunca preenchidos com coordenada chutada de outra rede).

### Amostra real

Boletim `2026-08-PLUVIOMETRIA-CGESP.xlsx`, dia 4 (todas as 0.0 mm — ver seção 5):

```
MO - Móoca            dia04=0.0  total_mes=30.6
SE - Sé               dia04=0.0  total_mes=39.6
IP - Ipiranga         dia04=0.0  total_mes=37.4
VM - Vila Mariana     dia04=0.0  total_mes=32.9
```

Página ao vivo, Vila Mariana (POSTO=495), últimas 24h reais em 15/09/2026
(`processo_cge_495_ref.html`):

```
15 SET 2026 07:00   Chuva(mm)=16.2  (acumulado do período desde zeramento 10:00 do dia anterior)
15 SET 2026 08:00   Chuva(mm)=0.0
15 SET 2026 23:00   Chuva(mm)=1.8
```

### Veredito

**`VIÁVEL_COM_RESSALVA`** — real, público, sem custo. Ressalvas: (1) resolução
diária no arquivo histórico (a página horária não tem histórico); (2) sem
coordenadas oficiais publicadas; (3) atraso de publicação de ~2-4 semanas no
boletim mensal, o que hoje deixa 2 das 3 sessões-alvo sem dado algum desta fonte.

---

## 3. SAISP / DAEE

### Acesso

- `https://www.saisp.br/` redireciona para um site estático + uma SPA Ionic
  ("Produtos Públicos", `/online/produtos-publicos`).
- Confirmado (seção 2) que o backend de telemetria de SAISP e CGE-SP é o mesmo
  (FCTH) — herda a mesma limitação de "só últimas 24h" sem navegação histórica.
- Existe um arquivo de **relatórios narrativos de eventos de chuva** em
  `https://www.saisp.br/historic/<AAAAMM>/dia<DD>/` (ex.:
  `.../historic/201201/dia19/`). Testamos `202608/` (existe) e `202609/` (**404**,
  pasta do mês nem existe ainda). Dentro de `202608/`, só há relatórios para os dias
  05, 06, 14 e 26 — **não existe relatório para 04/08** (reforça que não houve
  evento relevante nesse dia) e nenhum para os dias de setembro. Esses relatórórios
  são narrativos/pontuais (radar, alertas de nível de rio), não uma série temporal
  de estação — mesmo se existissem para nossas datas, não dariam uma série mm×tempo
  por estação.
- **Consulta Pública** (`https://consultapublica.spaguas.sp.gov.br/login`) —
  **exige login** (e-mail + senha, com fluxo de "esqueceu senha"). Não tentamos
  criar conta. **`BLOQUEADO_CADASTRO`.**
- **Banco de Dados Hidrológicos (DAEE convencional)**,
  `https://ph.spaguas.sp.gov.br/Pluviometricos` (domínio antigo
  `ph.daee.sp.gov.br` está com certificado TLS incompatível e não resolve mais) —
  catálogo público de postos pluviométricos **convencionais** (leitura manual), com
  coordenadas oficiais em graus/min/seg. **Sem cadastro.** Mas ao abrir o posto mais
  próximo da região (MOOCA, prefixo E3-246), os seletores de "Ano Inicial"/"Ano
  Final" só oferecem **1972–1999**; no posto LUZ (E3-036), o intervalo é
  **1999–2016**. Ou seja, **não há dado depois de 2016 em nenhum posto testado** —
  essa rede convencional parece ter sido descontinuada/substituída pela rede
  telemétrica (a mesma que CGE-SP/SAISP operam). **Sem dado para 2026 em nenhuma
  hipótese.**

### Resolução temporal

- Rede telemétrica (via CGE): horária, mas sem histórico além de 24h (ver fonte 2).
- Rede convencional (DAEE/ph.spaguas): diária/mensal, mas sem dado depois de ~2016.

### Cobertura histórica

Nenhuma via desta fonte cobre 2026.

### Estações próximas (rede convencional DAEE, coordenadas do catálogo `ph.spaguas.sp.gov.br`)

| Prefixo | Nome | Município | lat | lon | dist (km) | Dado até |
|---|---|---|---|---|---|---|
| E3-246 | MOOCA | São Paulo | -23.56667 | -46.61667 | 0.11 | 1999 |
| E3-253 | PARAISO | São Paulo | -23.56667 | -46.65000 | 0.11 | não verificado (mesma rede) |
| E3-036 | LUZ | São Paulo | -23.53333 | -46.63333 | 1.48 | 2016 |
| E3-090 | INSTITUTO BIOLOGICO | São Paulo | -23.58333 | -46.65000 | 1.96 | não verificado |
| E3-096 | PONTE PEQUENA | São Paulo | -23.51667 | -46.65000 | 3.33 | não verificado |
| E3-003 | AGUA BRANCA | São Paulo | -23.51583 | -46.68083 | 4.06 | não verificado |

(Coordenadas convertidas de graus/min/seg do próprio catálogo; distância haversine
ao ponto mais próximo dos 3 bboxes.)

### Amostra real

Não há amostra de 2026 para citar — nenhuma consulta no Banco de Dados Hidrológicos
devolveu dado depois de 2016 (print de tela do formulário de consulta do posto
MOOCA em `respostas_brutas/saisp/mooca_posto.html`, seletor de ano limitado a
1972-1999).

### Veredito

**`INVIÁVEL`** — a via sem cadastro (DAEE convencional) não tem dado para 2026 em
nenhum posto testado; a via com dado atual (telemetria) é a mesma da CGE-SP sem
histórico navegável; a via com histórico completo (Consulta Pública) exige
cadastro.

---

## 4. INMET

### Acesso

- Catálogo de estações: `GET https://apitempo.inmet.gov.br/estacoes/T` — funciona
  sem chave, **mas só responde com um User-Agent de navegador** (com o User-Agent
  padrão do `curl`, a conexão é resetada pelo servidor — não é bloqueio de
  autenticação, é алgum filtro de User-Agent). A701 (Mirante de Santana) e A771
  (Interlagos) confirmados no catálogo, com coordenadas oficiais.
- **A rota documentada na spec, `GET /estacao/{data_ini}/{data_fim}/{codigo}`, está
  quebrada/descontinuada**: testamos com A701/A771/A728 e datas de 2022 a 2026
  (inclusive datas certamente válidas e antigas) e **sempre voltou HTTP 204 (sem
  conteúdo)**, mesmo com header de navegador. Investigamos o bundle JS de
  `https://tempo.inmet.gov.br/` (site oficial que consome essa mesma API) e
  confirmamos que o frontend atual **não usa mais essa rota GET**: usa
  `POST /estacao/front/` com corpo `{data_inicio, data_fim, estacao, seed, gcap}`,
  onde **`gcap` é um token do Google reCAPTCHA v3** (`grecaptcha.execute(...)`,
  site key visível no bundle). Ou seja, o endpoint documentado na spec foi
  substituído por um endpoint protegido por captcha — não é cadastro de usuário,
  mas é uma barreira antibot equivalente que não vamos contornar (não resolvemos
  captcha de forma automatizada).
- **Alternativa real e funcional: arquivo histórico anual ZIP**,
  `https://portal.inmet.gov.br/uploads/dadoshistoricos/<ano>.zip` — **público, sem
  login, sem captcha**. Baixamos `2026.zip` (64 MB): contém um CSV por estação
  automática do Brasil, com dado horário. **O CSV de 2026 vai de 01/01/2026 até
  31/08/2026** (arquivo com timestamp interno de 02/09/2026 — atraso de ~2 dias
  após o fim do mês). **Não inclui setembro.**

### Resolução temporal

- ZIP anual: **horária**, "Hora UTC" já em UTC (documentado no próprio cabeçalho do
  CSV e confirmado nos dados).
- API `/estacao/front/` (viva, com captcha): também horária, mas inacessível sem
  resolver reCAPTCHA v3.

### Cobertura histórica

- ZIP anual cobre 01/01/2026–31/08/2026. **04/08/2026: coberto.** 01/09 e 13/09:
  **não cobertos** (mês ainda não fechado/publicado).

### Estações próximas

| Código | Nome | lat | lon | dist. à sessão mais próxima (km) |
|---|---|---|---|---|
| A701 | SÃO PAULO - MIRANTE (Mirante de Santana) | -23.4962888 | -46.6200666 | 5.59 (sessão 01/09) |
| A771 | SÃO PAULO - INTERLAGOS | -23.72444443 | -46.67749999 | 17.75 (sessão 01/09) |

Nenhuma das duas fica dentro do raio de 5 km — confirma o que a spec já apontava: o
INMET é o fallback de pior localização geográfica entre as 4 fontes.

### Amostra real

`INMET_SE_SP_A701_..._01-01-2026_A_31-08-2026.CSV`, 04/08/2026 (UTC):

```
2026/08/04;1000 UTC;0
2026/08/04;1100 UTC;0   <- cobre a janela da sessão (11:12-11:29 UTC = 08:12-08:29 local)
2026/08/04;1200 UTC;0
```

`INMET_SE_SP_A771_..._01-01-2026_A_31-08-2026.CSV`, 04/08/2026 (UTC): todas as 24
horas = 0, exceto `0700 UTC = 0,2 mm` (de madrugada, fora da janela da sessão).

### Veredito

**`VIÁVEL_COM_RESSALVA`** — o ZIP anual é real, gratuito, sem login/captcha, e
confirma o dia seco de 04/08. Ressalvas: resolução horária (não 10 min), estações a
5,6–17,8 km (fora do raio de 5 km da spec), e sem cobertura de setembro até a
publicação do próximo corte mensal/anual. A via "oficial" documentada na spec está
de fato descontinuada e substituída por uma rota com reCAPTCHA v3.

---

## 5. Validação de coerência (E3)

### Sessão 2026-08-04 (08:12–08:29 local = 11:12–11:29 UTC) — esperado ~0 mm

| Fonte | Estação | dist. | 10h UTC | 11h UTC | 12h UTC |
|---|---|---|---|---|---|
| INMET | A701 Mirante de Santana | 6.48 km | 0 mm | 0 mm | 0 mm |
| INMET | A771 Interlagos | 18.89 km | 0 mm | 0 mm | 0 mm |
| CGE-SP | Vila Mariana / Móoca / Ipiranga / Sé (total do dia) | n/d (sem coord.) | — | 0.0 mm (dia todo) | — |

Duas fontes independentes (INMET horário e CGE-SP diário) concordam: **0 mm** na
janela e no dia inteiro, em 4 estações da região. CEMADEN não pôde ser checado
(dia fora do alcance dos ~15 dias da via sem login).

**Veredito: `COERENTE`.**

### Sessão 2026-09-01 (07:32–08:51 local = 10:32–11:51 UTC) — esperado chuva > 0, decrescente

| Fonte | Estação | dist. | 08h UTC | 09h UTC | 10h UTC | 11h UTC | 12h UTC |
|---|---|---|---|---|---|---|---|
| CEMADEN (via B, ressalva de semântica) | Ipiranga | 2.18 km | 2.36 | 2.55 | 2.55 | 2.55 | 2.36 |
| CEMADEN (via B) | Luz | 1.73 km | 0.8 | 0.6 | 0.6 | 0.6 | 0.6 |
| CEMADEN (via B) | Mooca / AC Almeida Lima (0,00 km) | 0.00 km | 0 | 0 | 0 | 0 | 0 |
| INMET / CGE-SP | — | — | sem dado (mês não publicado) | | | | |

Leitura honesta: há **sinal real de chuva** em 2 das 3 estações CEMADEN mais
próximas checadas (Ipiranga e Luz), com valores altos justamente nas horas que
cobrem a janela da sessão, e um patamar (não crescimento) durante boa parte da
janela — compatível com "chovia, e por volta do meio da sessão já não estava mais
chovendo" (o relato visual de "gotas fortes → quase seco → esparsas"). Só que **duas
estações a 0,00 km (Mooca e AC Almeida Lima) registraram zero o dia todo**, o que
mostra que a chuva foi espacialmente bem localizada/heterogênea — plausível em
chuva convectiva de verão em São Paulo, mas é exatamente o tipo de resultado que a
spec pede para não maquiar. Como a semântica exata do campo "acumulado" desta via
não está confirmada (pode ser um acumulado móvel, não um delta limpo da hora), não
temos confiança para cravar `COERENTE` num nível fino de minuto — mas há evidência
real e não-trivial de chuva na região e no horário certos.

**Veredito: `COERENTE` (evidência qualitativa real, mas com ressalva de semântica
do dado e de heterogeneidade espacial — recomenda-se reconfirmar com a API oficial
do CEMADEN, que tem `acc1hr` bem documentado, assim que o cadastro PED estiver
disponível).**

### Sessão 2026-09-13 (16:31–16:53 local = 19:31–19:53 UTC) — esperado chuva fraca/pós-chuva

| Fonte | Estação | dist. | 18h UTC | 19h UTC | 20h UTC |
|---|---|---|---|---|---|
| CEMADEN (via B) | AC Central de SP | 0.37 km | 1.0 | 0.8 | 0.6 |
| CEMADEN (via B) | Ipiranga | 2.18 km | — | — | 0.6 |
| CEMADEN (via B) | Luz | 1.73 km | 0.2 | 0.0 | 0.4 |
| INMET / CGE-SP | — | — | sem dado (mês não publicado) | | |

Valores pequenos (0,2–1,0 mm) e em leve declínio na estação mais próxima (0,37 km),
exatamente na hora da sessão — consistente com "garoa/pós-chuva, rua molhada" e não
com chuva forte em curso. Mesma ressalva de semântica do campo acumulado da fonte
B do CEMADEN.

**Veredito: `COERENTE` (mesma ressalva de semântica de dado da fonte).**

### Resumo

| Sessão | Veredito |
|---|---|
| 2026-08-04 | `COERENTE` (alta confiança — 2 fontes independentes, dado horário limpo) |
| 2026-09-01 | `COERENTE` (confiança média — 1 fonte, semântica de acumulação não confirmada) |
| 2026-09-13 | `COERENTE` (confiança média — mesma ressalva) |

Nenhum resultado `INCOERENTE` foi encontrado. Isso é bom sinal para o alinhamento
espaço-temporal geral, mas **não é uma validação forte** para as sessões de
setembro: ela depende de um endpoint não documentado cuja semântica de acumulação
não foi confirmada. Se fosse necessário decidir hoje se o pipeline de rotulagem
funciona, o resultado seria "promissor, mas pendente de confirmação com a API
oficial (`acc1hr` documentado) após o cadastro PED".

---

## 6. Verificação de fuso horário (UTC)

- **INMET**: nativo em UTC (coluna "Hora UTC" do próprio arquivo). Nenhuma
  conversão foi feita — confirmado nos dados de 04/08 (ex.: linha `1100 UTC`).
- **CGE-SP**: o site declara explicitamente (modal de download) que "todos os
  dados são registrados em UTC" na página ao vivo, mas o boletim mensal em XLSX
  não expõe timestamp — é um total por dia civil. Assumimos dia civil local
  (America/Sao_Paulo, UTC−3) e gravamos `ts_utc` como `00:00 local → 03:00Z` do
  mesmo dia. **Essa é uma suposição documentada, não uma confirmação da fonte** —
  fica como risco em aberto se o "zeramento" real da CGE-SP não for meia-noite
  local (a página ao vivo de uma estação mostrou "Zeramento: 10:00:00", o que
  sugere que o dia do boletim pode não ser 00h-24h civil puro).
- **CEMADEN (via B)**: confirmado empiricamente como UTC (ver seção 1) comparando
  a última hora não-nula do dia corrente com o horário UTC real do sistema no
  momento da coleta.
- **Checagem do critério de aceite** ("a chuva de 01/09 deve aparecer entre 10:32 e
  11:51 UTC"): no CSV `cemaden.csv`, a estação Ipiranga tem
  `2026-09-01T10:00:00Z,2.35608` e `2026-09-01T11:00:00Z,2.35608` — dentro da janela
  pedida. `inmet.csv` e `cgesp.csv` não têm linhas de 01/09 (mês não publicado por
  nenhuma das duas fontes), então esse critério específico só pôde ser demonstrado
  com o CEMADEN.

---

## 7. Recomendação final

**Fonte principal recomendada: CEMADEN, via cadastro na API oficial (PED).**
Justificativa: é a única fonte com resolução nativa de 10 min, `acc1hr`/`acc24hr`
com semântica documentada, maior densidade de estações na região (15 estações
≤ 5 km, 4 delas < 1 km) e sem o atraso de publicação de semanas que atinge CGE-SP e
INMET. O cadastro em `https://ped.cemaden.gov.br/cadastrarUsuario` pede só Nome,
E-mail e Senha, e pelo fluxo do app parece ser auto-atendimento (sem aprovação
manual visível) — mas isso só será confirmado quando o Rodrigo de fato criar a
conta. **Passo a passo para o Rodrigo:**
1. Acessar `https://ped.cemaden.gov.br/cadastrarUsuario`, preencher Nome/E-mail/Senha.
2. Confirmar e-mail se solicitado (o app tem uma tela de "reenviar e-mail").
3. Logar em `/efetuarLogin`, gerar um token JWT via `/controle-token/tokens` (rota
   usada pelo próprio frontend — não documentada isoladamente no Swagger, mas
   referenciada em todos os endpoints como "recuperado pelo webservice
   /controle-token/tokens").
4. Usar o token no header `token` dos endpoints `GET /pcds-acum/acumulados-historicos`
   (acumulados por hora, já processados) e/ou `GET /pcds/dados_pcd` (dado bruto, até
   30 dias por chamada) descritos em `respostas_brutas/cemaden/ped_swagger3.json`.

**Plano B, sem esperar cadastro (disponível hoje):** combinar as 3 fontes
já-públicas conforme a data:
- Para dias com mais de ~1 mês (como será o caso da maior parte da coleta, dado o
  cronograma): **CGE-SP** (boletim mensal XLSX, diário, sem coordenadas — só serve
  para validação grosseira "choveu no dia" vs "dia seco") e **INMET** (ZIP anual,
  horário, estações longe — serve de segunda opinião independente).
- Para dias muito recentes (últimos ~15 dias, o caso mais comum durante a coleta
  ativa): **CEMADEN via B** (`mapservices.cemaden.gov.br/.../horario/<id>/<horas>`),
  sem cadastro, mas tratando o "acumulado" só como indício qualitativo até a
  semântica ser confirmada com a via A.
- Em nenhum caso usar o DAEE convencional (`ph.spaguas.sp.gov.br`) — sem dado desde
  ~2016/1999, nem tentar `/estacao/front/` do INMET (reCAPTCHA) ou
  `consultapublica.spaguas.sp.gov.br` (login) sem decisão explícita do Rodrigo.

**O que degrada, e o impacto real no pipeline de rotulagem:**
- **Sem cadastro CEMADEN**: a janela de rotulagem de ±15 min não é atingível para
  frames coletados há mais de ~1 mês (só sobra CGE-SP diário e INMET horário/longe)
  — isso praticamente inviabiliza rotular retroativamente qualquer coleta antiga
  sem esperar 1 mês por INMET/CGE-SP, ou sem o cadastro CEMADEN.
  Impacto: rotulagem em lote só é viável (a) quase em tempo real (≤15 dias, via
  CEMADEN B, qualitativo) ou (b) com defasagem de ~1 mês (via INMET/CGE-SP,
  diário/horário longe). Nenhuma opção dá 10 min + ≤2 km + sem espera simultaneamente
  sem o cadastro CEMADEN.
- **Se usar só INMET (fallback puro)**: janela de rotulagem degrada de ±15 min para
  a hora cheia inteira (60 min), e a estação mais próxima fica a 5,6-6,5 km da
  sessão (acima do corte de 2 km da spec) — qualquer classe "moderada"/"forte" que
  dure poucos minutos pode ser diluída/perdida numa média horária a quilômetros de
  distância.
- **Se usar só CGE-SP**: janela degrada de ±15 min para o dia inteiro (1440 min) —
  serve só para descartar grosseiramente "dia claramente seco" vs "choveu bastante
  nesse dia", não para rotular a intensidade de um frame específico.

---

# ADENDO — 16/09/2026: API oficial do PED destravada

> Atualiza as seções acima. O veredito do CEMADEN muda de `BLOQUEADO_CADASTRO`
> para **`VIÁVEL`**: o Rodrigo fez o cadastro em ped.cemaden.gov.br e a API
> oficial foi acessada com sucesso, em resolução de **10 minutos**.

## Resultado

`ml/data/raw/estacoes/normalizado/cemaden_ped.csv` — **1.281 leituras**:

| Dia-alvo | Leituras | Estações |
|---|---:|---:|
| 2026-08-04 | 236 | 11 |
| 2026-09-01 | 689 | 11 |
| 2026-09-13 | 356 | 7 |

Resolução de 10 min confirmada (leituras em :00, :10, :20... durante eventos de
chuva; em períodos secos a série fica horária). A resposta declara o fuso no
próprio corpo: `OBS.: PCD com horario UTC!`.

## Validação de coerência — as 3 sessões batem

| Sessão | Esperado (visual) | Observado na estação | Veredito |
|---|---|---|---|
| 04/08 11:12–11:29Z | seco | nenhuma leitura > 0 na janela | **COERENTE** |
| 01/09 10:32–11:51Z | chuva com transição | chuva em Ipiranga, Luz, Limão, Centro; dia acumulou 28,8 mm (Ipiranga) e 38,8 mm (V. Prudente) | **COERENTE** |
| 13/09 19:31–19:53Z | garoa / pós-chuva | 0,2 mm em AC Central de SP, Luz, S.Caetano | **COERENTE** |

**Consequência para o plano:** o maior risco declarado em `docs/plano-dataset.md`
(F1.1 — "histórico de estação inacessível") está **eliminado**. O alinhamento
espaço-temporal câmera ↔ estação funciona e pode servir de ground truth.

## Como acessar (o que custou a descobrir)

`ml/scripts/estacoes/baixar_cemaden_ped.py` já encapsula tudo. Os detalhes não
documentados publicamente:

1. **Host do login é `ped.cemaden.gov.br`, não `sws.`** — o SPA usa axios com
   `baseURL:""`, então a rota `/SGAA/rest/controle-token/tokens` é relativa à
   origem do front. Em `sws.` ela devolve 404.
2. **Corpo do login:** `{"email": ..., "password": ...}` (classe `Credential` do
   backend rejeita `usuario`/`login`/`cpf` como "Unrecognized field").
3. **Datas no formato `aaaaMMddHHmm`** (ex.: `202609010000`), não ISO.
4. **`sensor=10`** (id numérico de "Chuva"); a string `"chuva"` é rejeitada.
5. **O token tem cota baixa de usos** (401 "excedeu o número máximo total de
   acessos"). O script renova proativamente a cada 5 chamadas.
6. **A resposta é CSV com `;`, precedido da linha `OBS.: PCD com horario UTC!`** —
   o parser precisa pular linhas até o cabeçalho `cod.estacao;...`.

### Endpoint de dados ≠ endpoints de catálogo

`/pcds-cadastro/dados-cadastrais` e `/pcds-cadastro/estacoes` responderam
**HTTP 500** ("Falha na comunicação com o servidor!") de forma persistente em
15 e 16/09 — o que inicialmente foi interpretado como "serviço fora do ar".
**Não estava:** `/pcds/dados_pcd` respondia 200 normalmente no mesmo instante,
com o mesmo token. Lição: testar a disponibilidade no endpoint que se pretende
usar, nunca em outro.

# ADENDO 2 — 18/09/2026: semântica do `valor` confirmada e download completo

## `valor` = incremento de precipitação do intervalo de 10 min

A ressalva do adendo anterior está **resolvida**. Não é acumulado móvel. Duas
evidências independentes:

**1. Quantização na resolução da báscula.** Os 786 valores não-zero são múltiplos
inteiros de **0,19634 mm** — a resolução de tombo do pluviômetro CEMADEN. Os
valores de 2 tombos ou mais são múltiplos exatos (`0.39268` = 2×, `0.58902` = 3×,
`0.78536` = 4×, `0.9817` = 5×, `1.17804` = 6×, até 32 tombos = `6.29573`). Só o
caso de **1 tombo é reportado arredondado como `0.2`** em vez de `0.19634` (viés
de +1,9%, desprezível para classificação — mas documentar).

Um acumulado móvel não ficaria preso em 1–2 tombos durante horas de chuva
contínua: cresceria. O que parecia "constante em 0.393 por horas" no Ipiranga é
chuva fraca e **estável** — 2 tombos a cada 10 min = 2,36 mm/h, garoa persistente.

**2. Cruzamento com a via pública horária.** Somar os incrementos de 10 min
reproduz a série horária independente (`cemaden.csv`, Mapa Interativo) com
**MAE 0,070 mm e 74% de coincidência exata** (tolerância 0,05 mm). Tomar o
*último* ou o *máximo* do intervalo nunca reproduz. Varredura de defasagem em
passos de 10 min entre −4 h e +4 h: o ótimo é inequívoco em **+120 min**, ou
seja, o rótulo `Xh` da via pública corresponde à hora que *começa* em `X+1h`.
Isso fecha também a ressalva 1 do `normalizar_cemaden.py`: a via pública **é**
agregação horária de incrementos, só está rotulada com outra convenção.

### Conversão para rotulagem (F1.3)

```
mm_h = valor * 6          # janela de 10 min -> hora
```

| tombos | valor | mm/h | classe |
|---|---|---|---|
| 1 | 0,2 (arred.) | 1,2 | `garoa` |
| 2 | 0,39268 | 2,36 | `garoa` |
| 3 | 0,58902 | 3,53 | `moderada` |
| 32 | 6,29573 | 37,8 | `forte` |

O degrau mínimo de **1,2 mm/h** já previsto no plano está confirmado. A zona morta
de 15% dos limiares continua necessária: com 2 tombos = 2,36 mm/h, a fronteira
`garoa`/`moderada` (2,5) cai exatamente entre dois degraus possíveis.

## Download completo: 33 de 45 pares, e os 12 restantes não existem

`cemaden_ped.csv` passou de 1.281 para **1.642 leituras**. Recuperados os pares
que tinham falhado por cota (401): Vila Clementino, Limão, Pinheiros e Lapa em
13/09.

**Os 12 pares que continuam faltando não são falha de cota — a API responde
HTTP 202 "Nenhum resultado foi encontrado" para os 3 dias.** Quatro estações não
têm série nenhuma no período:

| Estação | Código | Situação |
|---|---|---|
| Mooca | 355030826A | 202 nos 3 dias |
| AC Almeida Lima | 355030831A | 202 nos 3 dias |
| Vila Formosa | 355030877A | 202 nos 3 dias |
| Vila Maria | 355030854A | 202 nos 3 dias |

⚠️ **Impacto no plano:** Mooca e AC Almeida Lima eram justamente as duas estações
a ~0 km das rotas. Elas **não podem ancorar o ground truth**. As mais próximas
com dados reais passam a ser as candidatas de F1.3 — recalcular distâncias
frame↔estação apenas sobre as 11 estações que reportam.

**Cota é do cadastro, não do token.** Renovar o JWT não a reseta: o script
renovou e ainda tomou 401 na mesma sequência. E as consultas às estações sem
dados **gastavam a cota inteira antes de chegar nos pares recuperáveis** — por
isso o script agora cacheia a negativa 202 e a pula (`--forcar` reconsulta).

## Classes disponíveis dentro das janelas reais de sessão

Aplicando os limiares às leituras de 10 min (janela da sessão ±30 min):

| Sessão (UTC) | seco | garoa | moderada | forte | máx. observado |
|---|---|---|---|---|---|
| 04/08 11:12–11:29 | 14 | 0 | 0 | 0 | 0,0 mm/h |
| 01/09 10:32–11:51 | 11 | 72 | **4** | 0 | 3,5 mm/h (Vila Prudente, Ipiranga) |
| 13/09 19:31–19:53 | 6 | 25 | 0 | 0 | 1,2 mm/h |

Há `forte` no dia 01/09 — Vila Prudente chega a **37,8 mm/h às 06:20 UTC** — mas
entre 03:50 e 07:00 UTC, **horas antes** da sessão (que começa 10:32). Não há
frame nosso nesse intervalo.

**Conclusão para o plano:** a premissa "`forte` fica vazia até outubro" **se
confirma**; a de que `moderada` também ficaria **não** — existem 4 leituras
`moderada` dentro da janela de 01/09. Quantos frames de fato caem a ≤ 2 km
dessas estações nesses minutos é o que F1.3 vai dizer.

## Pendências

- [ ] Recalcular a distância frame↔estação usando **só as 11 estações que
      reportam** (Mooca e AC Almeida Lima estão fora) — entra em F1.3.
- [ ] Os dias-alvo cobrem só as sessões já coletadas; a coleta de outubro exigirá
      novas chamadas (o script recebe `--dias`).
- [ ] Cota do cadastro limita ~11 chamadas por rodada; para outubro, planejar o
      backfill em lotes ou pedir aumento de cota ao CEMADEN.

## irCNN (Yin et al. 2023) — teste real de moderada/forte

- **Fonte:** https://doi.org/10.6084/m9.figshare.22122500.v1 (figshare 22122500; Yin et al., "Estimating Rainfall Intensity Using an Image-Based Deep Learning Model", *Engineering* 21, 2023). Baixado em 30/09/2026 para `ml/data/raw/public_datasets/ircnn/` (12 vídeos `Event N.mp4`, ~230 MB cada, + `Gauge-observations.xlsx`; total 2,8 GB). Não há README no figshare (descrição: "Rainfall videos and the rainfall data measured by a rain gauge").
- **Licença:** CC BY 4.0 (citar Yin et al. 2023 e Zheng et al. 2023, WRR, 10.1029/2023WR034831).
- **O dataset tem 12 eventos** (6 diurnos, 7-12 noturnos em IR/cinza), não 6. Câmera fixa de vigilância em Hangzhou, 1920x1080, 1 fps, 60 min por vídeo (jun-jul/2020).
- **Rótulo:** pluviômetro de báscula a 1-2 m da câmera, 1 leitura por minuto (hh:mm:45), resolução 0,1 mm/min (= 6 mm/h). A planilha **não declara a unidade**; ela é **mm/min** (Zheng et al. 2023, seção 3 e Tabela 1: máx. 156 mm/h no evento 10 = 2,6 mm/min). Convertido para mm/h (x60). Consequência: toda leitura > 0 vale >= 6 mm/h; só a interpolação gera garoa.
- **Alinhamento temporal:** o relógio do vídeo é a tag `creation_time` (UTC) + 8 h, conferida contra o timestamp gravado no frame (ex.: evento 10, frame 0 = 2020-07-02 20:00:13). Frame t = início + t s. Entre leituras do pluviômetro usa-se interpolação linear (Eq. 14 de Zheng et al.). Frames fora da janela do pluviômetro (que cobre só o evento, 12-69 min de cada vídeo) são descartados; zona morta de ±15% de 2,5 e 10 mm/h descartada.
- **Ressalvas:** domínio diferente (vigilância fixa, sem para-brisa; 7-12 em infravermelho noturno); o `seco` do irCNN (74 frames) é só zero interpolado dentro de evento, pode ter chuva abaixo da resolução do báscula — não usar como teste de seco. Extração: `ml/scripts/dataset_publico/ircnn_extrair.py`; frames reduzidos para 960x540.
