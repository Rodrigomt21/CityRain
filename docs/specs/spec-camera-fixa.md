# SPEC CF — Modelo e pipeline de câmera fixa

> **Documento autocontido.** Tudo que é necessário para executar está aqui. Em caso de conflito
> entre esta spec e o estado real dos dados ou do código, **pare e reporte a divergência** em vez
> de improvisar.
>
> Projeto: CityRain (TCC IMT). Convenções do repo: PEP 8, type hints em funções públicas,
> docstrings Google style, nomes de variáveis em inglês, comentários em português.
> Commits `tipo: descrição` em português.
>
> Escrita em 2026-10-08. **Prazo duro: 20/10/2026.** O escopo de 4 classes não muda.
> Responsáveis: ML e dados — Rodrigo e Guilherme; backend — Moreno; frontend — Paulo.

## 1. Por que esta spec existe

Em 08/10 o orientador apontou risco de reprovação: o modelo atual mistura carro, câmera fixa e
sintético, e não há como provar onde ele funciona. A resposta é **separar os domínios**:

| | Câmera móvel (carro) | Câmera fixa (esta spec) |
|---|---|---|
| Entrada | Jetson → `/ingest` | coletor → `/ingest`, **sem Jetson** |
| `seco` decidido por | gate na Jetson | o próprio modelo fixo (4 classes) |
| Modelo | `intensidade_movel.onnx` (v3 atual) | `intensidade_fixa.onnx` (novo) |
| Dados de treino | só dado real do carro | **só dado real**, rótulo de pluviômetro |
| Sintético | no máximo como ablação | **nunca** |

O modelo fixo é a parte que dá para provar até 20/10, porque já existe chuva forte real com
pluviômetro em câmera fixa. Cada modelo é avaliado só no próprio domínio.

## 2. O que já temos (contado em 08/10)

**irCNN** (`ml/data/manifests/manifest_ircnn.csv`): câmera fixa de telhado em Hangzhou,
pluviômetro no local, **12 eventos**, 16.409 frames.

| | forte | moderada | garoa | seco |
|---|---:|---:|---:|---:|
| irCNN | 10.469 | 5.311 | 555 | 74 |

**Lives do YouTube com CEMADEN** (`ml/data/manifests/manifest_coleta_fixa.csv`): 12.428 frames de
30/09 a 05/10, 27 eventos, rotulados pela regra estrita.

| Câmera | garoa | moderada | seco | excluídos |
|---|---:|---:|---:|---:|
| `sp_centro_geolan` | 2.349 | 22 | 986 | 2.301 |
| `guaruja_enseada` | 390 | 0 | 0 | 1.363 |
| `bc_atlantica` | 250 | 20 | 10 | 1.434 |
| `ubatuba_tenorio` | 90 | 0 | 0 | 995 |
| `santos_gonzaga`, `praiagrande_boqueirao` | 0 | 0 | 0 | 2.213 |

Principal motivo de exclusão: `poucas_estacoes_consenso` (5.837) e `seco_incerto` (2.184).

**Código pronto:** `coletor.py` (frame ao vivo a cada N s, contrato da Jetson),
`recuperar_dvr.py --onde-choveu` (baixa do DVR de 120 h só os minutos em que choveu),
`baixar_cemaden_ped.py`, `gerar_manifest.py` (rotulagem por estação), treinador com CV por
evento, `exportar_onnx.py`, `/ingest` com inferência ONNX no backend.

**Desequilíbrio que precisa ser tratado:** `forte` existe só no irCNN; no Brasil, até agora, só
garoa e pouca moderada. Sem cuidado, o modelo aprende "cena do irCNN ⇒ forte". As regras de
CF3 e CF4 existem para isso.

## 3. CF1 — Fontes de câmera

### Regra de ouro

Só **transmissões publicadas de propósito**: lives públicas do YouTube, câmeras de prefeituras,
concessionárias de rodovia e emissoras que publicam imagem aberta, além de dispositivos da
própria equipe. **Nunca** câmeras IP "expostas" por falta de senha (listas tipo Insecam,
Shodan): isso é acesso não autorizado a equipamento de terceiros e não pode entrar num TCC.

### Critérios para aceitar uma câmera

1. Pública, estável (no ar há pelo menos uma semana) e com imagem de céu, rua ou paisagem.
2. **Pluviômetro CEMADEN com dado a ≤ 2 km**, ou pelo menos 3 estações a ≤ 5 km (consenso).
   Conferir com `ml/scripts/estacoes/distancia.py`.
3. Posição **verificada**: a lat/lon atual em `coleta_fixa.yaml` é aproximada pelo título da
   live. Confirmar no Google Maps pelo que aparece na imagem e corrigir antes de rotular
   (campo `posicao_verificada: true`).
4. Preferir regiões com chuva forte frequente em outubro: litoral de SP, capital e Sul.

### Tarefas

- **CF1.1** — Verificar a posição das 6 câmeras ativas e marcar `posicao_verificada`.
- **CF1.2** — Levantar de 4 a 6 câmeras novas que cumpram os critérios (prioridade: capital
  de SP, onde a rede CEMADEN é densa e há `seco` confirmável). Registrar em `coleta_fixa.yaml`
  com `fonte_publica:` (URL da página oficial que publica a câmera).
- **CF1.3** — Ver por que `santos_gonzaga` e `praiagrande_boqueirao` não rotulam nada:
  provavelmente faltam estações da cidade em `baixar_cemaden_ped.py`.

## 4. CF2 — Coleta e metadados

### Formato de cada frame (igual ao da Jetson)

`frame_AAAAMMDD_HHMMSS_mmm.jpg` + `.json`:

```json
{
  "device_id": "fixa-sp_centro_geolan",
  "capturado_em_utc": "2026-10-09T18:40:01.587Z",
  "gps": {"lat": -23.5465, "lon": -46.6340, "fixo": true, "ultimo_fix_em": "<= capturado_em_utc>"},
  "fonte": {"id": "sp_centro_geolan", "tipo": "youtube", "url": "...", "origem_tempo": "walltime_dvr|relogio_coletor"},
  "periodo": "dia|noite"
}
```

O horário vem do `Ingestion-Walltime-Us` do segmento (DVR) ou do relógio do coletor (ao vivo),
sempre em UTC.

### Dois fluxos, com papéis diferentes

| Fluxo | Para quê | Frequência |
|---|---|---|
| **Dataset** (`recuperar_dvr.py --onde-choveu` + `coletor.py`) | treino e teste | DVR a cada 2 dias (o DVR guarda 120 h); coletor a cada 10 min para `seco` e variedade dia/noite |
| **Ao vivo** (`coletor.py --enviar`) | dashboard e demo | 1 frame por câmera a cada 60 s → `POST /api/v1/ingest` |

- **CF2.1** — `coletor.py --enviar`: além de gravar em disco, envia cada frame ao `/ingest`
  com o token da câmera (um dispositivo por câmera, ver CF6). O frame continua no disco, porque
  pode virar dado de treino depois que o CEMADEN publicar a leitura.
- **CF2.2** — Onde roda: na demonstração, no Mac (`caffeinate -i`). Se der tempo, como serviço
  *worker* no Railway, com `yt-dlp` e `ffmpeg` na imagem.
- **CF2.3** — Rotina a cada 2 dias, de dia (o Mac não fica ligado à noite):
  `baixar_cemaden_ped.py --dias 3` → `recuperar_dvr.py --onde-choveu --desde <última colheita>`
  → `gerar_manifest.py --config ml/configs/rotulagem_coleta_fixa.yaml`.

## 5. CF3 — Rótulo: seco, garoa, moderada e forte

O rótulo vem **sempre de pluviômetro**, nunca do olho. Valem os mesmos limiares do projeto:

| Classe | mm/h |
|---|---|
| `seco` | 0, e **nenhuma** estação a ≤ 5 km com chuva em ±60 min |
| `garoa` | 0 < i ≤ 2,5 |
| `moderada` | 2,5 < i ≤ 10 |
| `forte` | > 10 |

Regras (já implementadas em `rotulagem_coleta_fixa.yaml`; não mudar sem registrar):

1. Estação mais próxima a ≤ 2 km, com janela de ±15 min centrada no frame. mm/h = soma dos
   incrementos de 10 min ÷ horas cobertas.
2. Sem estação a 2 km: **consenso regional**, em que ≥ 3 estações a ≤ 5 km caem na mesma
   classe. Campo heterogêneo é excluído, nunca interpolado.
3. **Zona morta** de ±15% em volta de 2,5 e 10 mm/h: o frame é descartado.
4. `seco` exige confirmação regional de ±60 min (zero isolado de báscula não prova seco).

Novidades desta spec:

- **CF3.1 — Revisão visual por amostra.** Para cada (câmera, classe), um painel com 24 frames
  aleatórios (`ml/data/review/camera_fixa/`). Uma pessoa marca câmera tampada, imagem congelada
  ou tela de "offline", e esses frames saem por regra (não por gosto). Os rótulos não são
  alterados à mão.
- **CF3.2 — Consenso a 5 km só para moderada e forte, com revisão.** Hoje a regra estrita dá
  42 moderadas e 0 fortes nas lives, e a 5 km seriam cerca de 412 moderadas e 10 fortes. Gerar
  um manifest paralelo `manifest_coleta_fixa_5km.csv`, que só entra no treino depois de passar
  pela revisão CF3.1. Reportar os dois números no texto.
- **CF3.3 — Unidade estatística é o evento.** Evento = sequência de frames da mesma câmera sem
  intervalo maior que 60 min. Splits e métricas são sempre por evento, nunca por frame.

## 6. CF4 — Dataset

| Partição | Conteúdo |
|---|---|
| Treino | eventos irCNN dos folds de treino + eventos das lives, **exceto a câmera de teste** |
| Validação | 1 evento irCNN + 1 evento de live por fold (para escolher época e limiar) |
| **Teste A — evento novo** | eventos irCNN fora do treino (CV de 4 folds, como na v3) |
| **Teste B — câmera nova** | `bc_atlantica` inteira, nunca vista no treino (*leave-one-camera-out*) |
| **Teste C — prospectivo** | toda chuva coletada de 13/10 a 18/10, congelada antes de olhar o resultado |

- **CF4.1 — Amostragem por (evento, classe):** no máximo 200 frames por (evento, classe) no
  treino, para o `forte` do irCNN não dominar. Peso de classe inverso à frequência, depois do teto.
- **CF4.2 — `seco` de todas as câmeras:** colher `seco` em dia e noite para **cada** câmera
  (meta: ≥ 300 por câmera). Sem isso, a câmera vira atalho para a classe.
- **CF4.3 — Dia e noite** são reportados separadamente em todas as métricas.
- **CF4.4 — Teste C** é a prova mais forte para a banca: dado que não existia quando o modelo foi
  desenhado. A data de congelamento fica registrada no manifest.

## 7. CF5 — Modelo e treino

O modelo fixo roda no **backend** (CPU do Railway, 1 frame por câmera por minuto), então não tem
a restrição de memória da Jetson. Mesmo assim, ficamos em modelos leves, porque o tempo de treino
cabe no prazo e as comparações ficam limpas.

**Saída:** 4 classes (`seco`, `garoa`, `moderada`, `forte`) e um score ordinal (classe esperada).
**Pré-treino:** ImageNet. **Entrada:** 288×384, a mesma do v3.

### Escada de experimentos (mesmo protocolo, mesmos folds)

| ID | O que muda | Por quê |
|---|---|---|
| **F0** | v3 atual aplicado direto nas câmeras fixas | referência: quanto se ganha separando o domínio |
| **F1** | MobileNetV3-Large, 4 classes, só dado real de câmera fixa | baseline do modelo fixo |
| **F2** | EfficientNet-B0 no lugar da MobileNetV3 | sem restrição de borda: vale testar um backbone maior |
| **F3** | F1/F2 + **referência seca da própria câmera** (2ª entrada: diferença entre o frame e um frame `seco` da mesma câmera no mesmo período do dia) | só a câmera fixa permite isso: o modelo vê o que mudou na cena, não a cena |
| **F4** (opcional) | 3 frames com 1 s de intervalo empilhados | riscos de chuva mudam entre frames; o fundo não |

**Por que o F3 é a aposta principal:** o maior risco do dataset é o modelo reconhecer a câmera
em vez da chuva (`forte` só aparece no irCNN). Com a diferença contra a mesma cena seca, a
informação de "qual câmera é" some em grande parte. A referência é escolhida automaticamente:
o frame `seco` confirmado da mesma câmera mais próximo em hora do dia.

### Regras do treino

- Validação cruzada por evento, 4 folds, na mesma divisão para F0 a F4.
- Época escolhida pela validação, **nunca** pelo teste. Modelo final com o número de épocas da
  mediana da CV (como na v3).
- Intervalo de confiança de 95% por bootstrap de evento e diferenças pareadas entre versões
  (`ml/scripts/avaliacao/`, já existe).
- Grad-CAM de cada versão por classe e por câmera: o modelo precisa olhar a chuva (névoa,
  riscos, pista molhada), não o carimbo nem o céu fixo.

### Critério de escolha (fixado antes de treinar)

1. Maior **F1 macro** no Teste A, desde que o IC 95% não fique abaixo do F1;
2. **recall de `forte` ≥ 0,7** no Teste A;
3. no Teste B (câmera nova), **acerto de `seco` × chuva ≥ 0,8** e Spearman score × mm/h > 0;
4. em empate estatístico, o modelo menor.

Configs: `ml/configs/treino_fixa_f{0..4}.yaml`. Saída: `ml/runs/fixa_f*`. Resumo em
`docs/resultados-experimentos.md`, seção nova "Câmera fixa".

## 8. CF6 — Backend

### Banco (migração Alembic)

`devices`:
- `tipo` — `'movel' | 'fixa'`, padrão `'movel'` (os dispositivos atuais continuam iguais);
- `latitude`, `longitude` — posição fixa (só para `fixa`);
- `stream_url`, `descricao` — de onde vem a imagem (só para `fixa`).

`captures`:
- `source_type` já existe: passa a valer `'jetson'` ou `'camera_fixa'`;
- `modelo` e `modelo_versao` — qual ONNX classificou (lido do `metadata_props` do arquivo).

### Ingestão

- O mesmo `POST /api/v1/ingest` e o mesmo contrato. Cada câmera fixa é um dispositivo com
  token próprio (`fixa-<id>`).
- Para dispositivo `fixa`: a posição vem do cadastro (ignora o GPS do JSON) e a classe vem do
  `intensidade_fixa.onnx`, com 4 classes.
- Para dispositivo `movel`: nada muda (gate na Jetson + `intensidade_movel.onnx`).
- O `InferenceService` passa a carregar **dois** modelos e escolhe pelo `device.tipo`. Se o
  modelo fixo não estiver carregado, grava a captura com classe nula, sem derrubar a ingestão
  (mesmo comportamento atual).

### Leitura

- `GET /captures` e `GET /stats/geo` ganham o filtro `tipo=fixa|movel`.
- **Novo** `GET /api/v1/cameras` (público): lista as câmeras fixas com posição, última captura,
  classe, confiança, URL da miniatura e a leitura do pluviômetro mais próximo.
- **Desejável:** `GET /api/v1/cameras/{id}/serie?horas=6`, com a série de classe prevista e o
  mm/h da estação, para o gráfico da demo.

### Pluviômetro ao vivo (desejável)

Um job a cada 10 min roda `baixar_cemaden_ped.py --dias 1` e grava as leituras das estações
próximas às câmeras numa tabela `station_readings`. Isso alimenta o "previsto × medido" no
dashboard. Se não der tempo, a demo usa os dados já baixados (CF8).

## 9. CF7 — Frontend

- **Mapa:** câmera fixa com ícone de câmera (quadrado) e o carro com um círculo, as duas
  coloridas pela classe. Filtro "Todas / Fixas / Móveis" no topo.
- **Nova página "Câmeras":** grade com uma card por câmera, com a miniatura do último frame,
  o selo da classe, a confiança, "há N min" e a **leitura do pluviômetro mais próximo ao lado**
  ("modelo: moderada · estação a 1,2 km: 6,4 mm/h").
- **Detalhe da câmera:** a série das últimas 6 h, com a classe prevista e o mm/h da estação no
  mesmo eixo de tempo (dois gráficos empilhados; nada de dois eixos y).
- Todo número que aparece vem da API. Nada fixo no código.

## 10. CF8 — Demonstração

Duas partes, as duas pelo pipeline de produção:

1. **Ao vivo:** 6 a 10 câmeras atualizando a cada 60 s na página "Câmeras". Se estiver chovendo
   em algum lugar no dia, ótimo; se não, mostra o `seco` correto.
2. **Replay de uma chuva real:** um evento do DVR com moderada ou forte (por exemplo
   `bc_atlantica` com 20 moderadas, ou um evento novo de outubro) reenviado frame a frame ao
   `/ingest`, com `metadata.demo = true`, no mesmo esquema do `demo_replay.py` da Jetson. A tela
   mostra o modelo subindo de garoa para moderada junto com o mm/h do pluviômetro.

Roteiro em `docs/roteiro-demo-defesa.md`, seção nova "Câmera fixa". O replay é preparado com
antecedência e ensaiado no dia 19/10.

## 11. Cronograma

| Data | ML e dados (Rodrigo, Guilherme) | Backend (Moreno) | Frontend (Paulo) |
|---|---|---|---|
| 08–09/10 | CF1.1, CF1.3, CF4.2 (seco), colheita DVR | migração `tipo` e colunas | ícones e filtro no mapa |
| 10–11/10 | CF3.1 e CF3.2, splits CF4, treino F0 e F1 | dois modelos no `InferenceService` | página "Câmeras" com dado de teste |
| 12–13/10 | F2 e F3, colheita DVR | `GET /cameras`, filtros, deploy | detalhe da câmera |
| 14–15/10 | escolha pelo critério, exportar ONNX fixo, `coletor --enviar` | modelo fixo em produção | integração com a API real |
| 16–17/10 | colheita DVR, Teste C congelado em 18/10 | job do pluviômetro (desejável) | ajustes |
| 18–19/10 | Teste C, Grad-CAM, texto dos resultados | replay da demo | ensaio da demo |
| **20/10** | **entrega: modelo, dataset e números** | | |

## 12. Riscos e o que fazer

| Risco | Resposta |
|---|---|
| `forte` só do irCNN: o modelo pode aprender a câmera | F3 (referência seca), teto por (evento, classe), Teste B por câmera e Grad-CAM. No texto, reportar o recall de `forte` separado por origem. |
| Pouca chuva forte no Brasil até 18/10 | DVR a cada 2 dias em todas as câmeras, CF3.2 a 5 km com revisão e mais câmeras no Sul e no litoral (CF1.2). |
| Posição aproximada das lives | CF1.1: nenhuma câmera rotula antes de `posicao_verificada`. |
| Live cai ou muda de URL | Várias câmeras, e o coletor registra a falha sem parar as outras. |
| `yt-dlp` quebra com mudança do YouTube | Atualizar o `yt-dlp` antes de cada colheita; `snapshot` como alternativa. |
| Deploy do backend trava (já aconteceu) | Datar o deploy pelo `/openapi.json` e ter o replay da demo funcionando também no backend local. |

## 13. Fora do escopo

- Câmeras sem autorização de publicação (ver CF1).
- Regressão em mm/h (a saída continua sendo 4 classes).
- Rodar o modelo fixo na Jetson.
- Sintético no modelo fixo.
