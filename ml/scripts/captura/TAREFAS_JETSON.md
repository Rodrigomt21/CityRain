# Tarefas na Jetson — semana de 28/09 a 04/10/2026

> Escrito em 28/09/2026, depois da rotulagem automática (F1.3) do plano de dataset.
> Público: quem for mexer na Jetson esta semana. Companheiro de `CLAUDE.md`
> (estado do hardware), `CONTRATO_API.md` (payload) e
> `MUDANCAS_NECESSARIAS_BACKEND.md` (perguntas pro Guilherme).

## Por que este documento existe

A rotulagem automática rodou em 18/09 e o resultado foi ruim: de **7.148 frames
com metadados, só 478 viraram rótulo** (351 `seco` + 127 `garoa`), com **zero
`moderada` e zero `forte`**. As três causas, em ordem de tamanho:

| motivo | frames | é culpa da Jetson? |
|---|---|---|
| estação a mais de 2 km da rota | 4.810 | não — planejamento de trajeto |
| **sem GPS fix** | **1.703** | **sim — é a maior perda evitável** |
| sem leitura de estação na janela | 157 | não |

Ou seja: **24% dos frames que já foram coletados são inaproveitáveis por causa
de metadado, não por causa de imagem**. A imagem está lá, boa, e não dá para
usar porque não se sabe onde nem exatamente quando foi tirada.

A estação chuvosa começa em outubro e a entrega é em novembro. A janela de
coleta de chuva forte é de ~8 semanas. **Cada sessão que sair com o metadado
quebrado é uma chuva que não volta.** Por isso o Bloco A abaixo vem antes de
qualquer trabalho de integração com a API: ele é pré-requisito da primeira
saída de outubro, não melhoria.

---

# Bloco A — Bloqueia a coleta de outubro (fazer ANTES da primeira chuva)

## A1. Gravar a hora do GPS (RMC) no metadado

**Problema.** `capturado_em_utc` vem de `datetime.now(timezone.utc)`, isto é, do
relógio do sistema — e a Jetson Nano **não tem RTC**. Se o `systemd-timesyncd`
não tiver sincronizado antes da captura (sem Wi-Fi no carro, boot rápido), o
timestamp sai errado e **não há como saber que saiu errado depois**. Foi isso
que matou as sessões de maio (19.037 frames com relógio corrompido, que não
casam com estação nenhuma).

O receptor NEO-6M já recebe a hora da constelação na sentença RMC, e o `gps.py`
já faz o parse dessa sentença — só joga a hora no lixo hoje. Gravar os dois dá
**duas fontes independentes**: se divergirem, sabemos na hora do
pós-processamento em vez de descobrir no fim.

**Onde.** `gps.py`. O `captura.py` não precisa de nada além do bump de schema,
porque ele já embute o dicionário inteiro do GPS (`"gps": le_gps()`) — campo
novo em `gps.py` aparece no metadado de graça.

Em `estado_inicial()`, dois campos novos:

```python
def estado_inicial():
    return {
        "fix": False,
        "latitude": None,
        "longitude": None,
        "altitude_m": None,
        "satelites": None,
        "hdop": None,
        "status_rmc": None,
        "hora_rmc_utc": None,    # NOVO (A1): hora vinda da constelação, não do relógio do sistema
        "ultimo_fix_em": None,   # NOVO (A2): quando o último fix válido foi visto
        "atualizado_em": None,
    }
```

No braço do RMC dentro de `processa_linha()`:

```python
        if isinstance(msg, pynmea2.types.talker.RMC):
            estado["status_rmc"] = msg.status
            # A hora do RMC vem da constelação GPS, independente do relógio da
            # Jetson (que não tem RTC). Duas fontes = timestamp auditável: se
            # divergirem no pós-processamento, a sessão é descartável de forma
            # consciente em vez de silenciosamente errada.
            if msg.status == "A" and msg.datestamp and msg.timestamp:
                estado["hora_rmc_utc"] = datetime.combine(
                    msg.datestamp, msg.timestamp, tzinfo=timezone.utc
                ).isoformat()
            estado["atualizado_em"] = agora
            return True
```

Cuidado com uma pegadinha do pynmea2: dependendo da versão, `msg.timestamp` já
vem com `tzinfo=UTC`. O `tzinfo=` do `datetime.combine()` sobrescreve — como
as duas coisas são UTC, o resultado é o mesmo nos dois casos. Não precisa
tratar, mas não se assuste ao ler.

Em `captura.py`, subir o schema para marcar que o metadado mudou de formato:

```python
            metadado = {
                "schema": 2,   # era 1; 2 = gps traz hora_rmc_utc e ultimo_fix_em
```

O contrato com o backend **não muda** — esses campos ficam só na Jetson, o
`uploader.py` não os envia (ver `CONTRATO_API.md`).

**Aceite:**
- [ ] JSON novo tem `gps.hora_rmc_utc` preenchido quando há fix, `null` sem fix
- [ ] bancada com NTP ok: `|capturado_em_utc − gps.hora_rmc_utc| < 2 s`
- [ ] teste de sabotagem: com o Wi-Fi desligado e o relógio errado de propósito
      (`sudo date -s "2020-01-01"`), o `hora_rmc_utc` continua certo e a
      divergência aparece nos dois campos — é exatamente o caso que queremos detectar
- [ ] **deployado na Jetson**, não só commitado no repo

## A2. Registrar quando o último fix aconteceu

**Problema.** Hoje, quando o fix cai, o `gps.py` faz `estado["fix"] = False`
mas **mantém `latitude`/`longitude` com os valores do último fix** (ele só
sobrescreve lat/lon quando `fix` é verdadeiro). Isso não é bug — é até útil —
mas quem lê o metadado não tem como saber se aquela coordenada é de 2 segundos
atrás ou de 20 minutos atrás. O `atualizado_em` não serve: ele é atualizado a
cada sentença NMEA, inclusive as que reportam ausência de fix.

Com `ultimo_fix_em`, a rotulagem pode aproveitar frames de fix recente: a 40
km/h, 5 segundos são ~55 m, muito abaixo do raio de 2 km da estação. **É assim
que se recupera boa parte dos 1.703 frames perdidos** sem coletar nada de novo.

**Onde.** `gps.py`, no braço do GGA:

```python
            if estado["fix"]:
                estado["latitude"] = msg.latitude
                estado["longitude"] = msg.longitude
                estado["altitude_m"] = msg.altitude
                estado["ultimo_fix_em"] = agora   # NOVO (A2)
```

E **não limpar** `ultimo_fix_em` nem `hora_rmc_utc` no trecho que degrada o fix
por silêncio (`SILENCIO_MAX_S`) nem no `except serial.SerialException`: o valor
antigo é justamente o registro de quão velha a posição é. Só `fix` vira `False`.

**Aceite:**
- [ ] com fix, `ultimo_fix_em` avança junto com o GGA
- [ ] arrancando a antena: `fix` vira `False`, `latitude`/`longitude` seguem
      preenchidos e `ultimo_fix_em` **congela** no instante do último fix bom
- [ ] religando a antena, `ultimo_fix_em` volta a avançar

## A3. Não apagar frame nenhum durante as sessões de coleta

**Problema, e é o mais perigoso desta lista.** O `uploader.py` chama
`apaga_par()` depois de um 2xx do backend — apaga o jpg e o json locais. Isso
está certo em produção (a Jetson não é arquivo, é sensor). Mas **esta semana o
pipeline vai ser apontado para a API real, e em seguida vêm as sessões de
outubro**. Se as duas coisas se cruzarem sem cuidado, os frames de chuva vão
subir, o backend vai responder 2xx, e o **único registro local desaparece** —
e é o registro local que a rotulagem (`gerar_manifest.py`) lê para produzir o
dataset do TCC.

Somando ao caso `seco`, que já vai para `sem_chuva_pendente/` e não sobe: sem
uma trava, uma sessão de chuva boa pode acabar com os frames espalhados entre
o backend e uma pasta de pendentes, e o dataset fica sem ela.

**Onde.** `cityrain_config.json`, dois campos novos:

```json
  "modo_coleta": true,
  "pasta_arquivo_coleta": "/home/jetson/frames/arquivo_coleta"
```

E em `uploader.py`, `apaga_par()` passa a **mover em vez de apagar** quando
`modo_coleta` estiver ligado (mesmo padrão que `move_para_pendente_seco()` já
usa, então é pouco código novo). O resto do fluxo não muda: o gate continua
decidindo o que sobe, a economia de banda continua valendo — só o descarte
local é que fica suspenso.

Regra de operação: **`modo_coleta: true` durante todo outubro.** Só volta para
`false` em demonstração/produção, quando não estivermos mais construindo
dataset. Vale um aviso no log a cada arranque do uploader dizendo em qual modo
está, para ninguém descobrir depois.

**Aceite:**
- [ ] com `modo_coleta: true`, depois de um 2xx o par aparece em
      `arquivo_coleta/` e some da fila (não fica reenviando em loop)
- [ ] com `modo_coleta: false`, comportamento atual preservado (apaga)
- [ ] uploader loga o modo no arranque
- [ ] disco aguenta: uma sessão de 60 min a 1 fps ≈ 3.600 pares — conferir
      espaço livre antes de sair (o `captura.py` já pausa abaixo de 500 MB)

## A4. Checklist pré-saída e escolha de trajeto

Os 4.810 frames perdidos por distância não são problema de código, são de
trajeto — e duas estações que passavam a ~0 km das rotas de 04/08 e 13/09
(**Mooca** e **AC Almeida Lima**) simplesmente **não reportam dado nenhum**: a
API do CEMADEN responde 202 "nenhum resultado" para elas nos três dias. Não
adianta passar perto delas.

Estas são as **11 estações que de fato entregaram leitura** nos dias testados.
O trajeto tem que passar a **≤ 2 km de pelo menos uma delas**, de preferência
ficar perto por boa parte da sessão:

| Estação | lat | lon |
|---|---|---|
| AC Central de SP | −23,54331 | −46,63599 |
| AC Santana | −23,50248 | −46,62884 |
| Centro | −23,54100 | −46,62900 |
| Centro (S.Caetano) | −23,60900 | −46,57300 |
| Ipiranga | −23,58700 | −46,60200 |
| Lapa | −23,52200 | −46,69500 |
| Limão | −23,51100 | −46,66700 |
| Luz | −23,53102 | −46,63253 |
| Pinheiros | −23,56300 | −46,70300 |
| Vila Clementino | −23,59900 | −46,65000 |
| Vila Prudente | −23,58400 | −46,56100 |

Os 478 rótulos que existem hoje vieram de AC Central de SP (0,37 km da rota de
01/09) e Centro (0,62 km) — a prova de que ficar perto funciona.

**Checklist para imprimir e deixar no carro:**

1. `timedatectl` mostrando `System clock synchronized: yes` **antes** de sair
   de casa (com Wi-Fi ainda pegando)
2. `gps.json` com `"fix": true` e `hora_rmc_utc` preenchido — conferir antes de
   dar partida, não no meio do caminho
3. `cityrain_config.json` com `"modo_coleta": true`
4. Espaço em disco: `df -h /home/jetson/frames` com folga para a sessão inteira
5. Câmera na orientação de sempre — olhar um frame no local (a inversão de 180°
   é conhecida e tratada no pós, mas mudar de orientação no meio da coleta cria
   uma terceira variante para tratar)
6. Trajeto escolhido na tabela acima, conferido no mapa antes de sair
7. Sessão de 30–60 min, mantendo 1 fps

**Depois de cada sessão, no mesmo dia:** copiar os frames para o Mac, rodar
`gerar_manifest.py` e commitar o manifest. Se o número de rótulos vier baixo, é
melhor descobrir no mesmo dia — dá tempo de corrigir o trajeto na próxima chuva.

---

# Bloco B — Pipeline completo contra a API real

Tudo aqui é o que você já planejava fazer esta semana. A ordem importa: **B1 e
B2 são bloqueios externos** (dependem do Guilherme), então mande as perguntas
antes de começar a mexer no código, para não ficar parado esperando.

## B1. Sair do placeholder: URL real e `api_key`

`cityrain_config.json` ainda tem `"backend_url": "http://127.0.0.1:8080/upload"`
e `"token": null`. A API real está em
`https://api-production-046f.up.railway.app`, endpoint `POST /api/v1/ingest`, e
**toda a API exige `HTTPBearer`**.

O `api_key` sai de `POST /api/v1/devices/` e **aparece uma única vez na
resposta** — não tem como recuperar depois, só re-registrar. Registrar como
`hw_model: "jetson_nano"` (o exemplo do schema diz `jetson_xavier`, o hardware
real é Nano). As duas opções estão escritas no item 4 do
`MUDANCAS_NECESSARIAS_BACKEND.md`; escolha uma com o Guilherme antes de tentar.

**Aceite:**
- [ ] device registrado, `api_key` no `cityrain_config.json` (arquivo fora do git)
- [ ] um par real sobe para a API de produção e volta 2xx
- [ ] aparece no dashboard

## B2. O caso `seco` não tem endpoint

`POST /api/v1/ingest` exige `image`. Quando o gate diz `sem_gota` a Jetson não
manda foto, e hoje não existe forma de dizer "aqui estava seco" sem imagem — por
isso `move_para_pendente_seco()` é um esqueleto que só move arquivo. Item 1 do
`MUDANCAS_NECESSARIAS_BACKEND.md`: endpoint novo, ou `image` opcional quando
`weather_label == "seco"`. Precisa da decisão dele para fechar o fluxo.

## B3. Confirmar a cascata com o Guilherme

O `info.description` da API ainda diz que a Jetson entrega tudo classificado, e
o `ml_service.py` assume isso. **Não é o desenho atual.** O desenho é cascata:

```
[Jetson] gate BINÁRIO chuva/seco  →  [Backend] 3 CLASSES garoa/moderada/forte  →  [Dashboard]
     só frames com chuva sobem          roda na ingestão                          4 classes ponta a ponta
```

O modelo que roda embarcado é binário e vai continuar binário. Quem transforma
em `garoa`/`moderada`/`forte` é o backend, na ingestão. Isso é o item 2 do
`MUDANCAS_NECESSARIAS_BACKEND.md` e continua sem resposta — vale cobrar, porque
muda o que ele precisa implementar.

Ressalva honesta para passar junto: **o classificador de 3 classes ainda não
existe treinado**, e pela rotulagem de 18/09 não há dado para treinar (zero
`moderada`, zero `forte`). O backend precisa da porta aberta para recebê-lo, não
do modelo pronto agora.

## B4. Baixar o limiar do gate de 0,5 para 0,3

Falso positivo custa banda; falso negativo custa um alerta de chuva que não
acontece. A assimetria justifica o limiar mais permissivo. Já é campo de config
(`limiar_chuva`), então é só editar — mas com `modo_coleta: true` o efeito
prático é pequeno em outubro (nada é descartado de verdade), e o que vale medir é
o recall sobre o dataset, no Mac. **Mudar, mas não confiar no número sem medir.**

## B5. `metadata` como schema tipado (item 3 do doc do backend)

Hoje `metadata` é `string` livre no OpenAPI. Errar nome de campo ou mandar
`confidence` em 0–100 em vez de 0–1 só quebra em runtime. Pedido de baixo custo
e que evita uma classe inteira de bug silencioso.

## B6. Suavização temporal (item 5 do doc do backend)

O gate decide frame a frame. Um limpador de para-brisa passando na hora errada
gera um `seco` isolado no meio de chuva real — e, como `seco` não sobe, o frame
desaparece sem rastro. Duas saídas: debounce local (só tratar como seco depois de
N frames seguidos) ou o backend suavizando com o histórico. **Em outubro isso
está coberto de graça pelo `modo_coleta`** (nada se perde localmente), então não
é urgente — mas é urgente para a demonstração final.

---

# Bloco C — Pendências antigas, quando sobrar tempo

Nada aqui bloqueia coleta nem integração. Está listado para não sumir.

- **TensorRT não instalado** (falta o `apt` com sudo). O `onnxruntime-gpu` já faz
  ~95–100 ms/frame em CUDA, folgado para 1 fps — então isso é otimização, não
  necessidade.
- **Debounce do botão de shutdown** implementado em 29/07 e **nunca validado com
  pressão física real**.
- **Fiação do GPS** registrada como feita; se alguma sessão de outubro vier com
  fix ruim desde o início, reconferir contato físico antes de culpar software.
- **`~/frames/sem_chuva_pendente/`** acumula desde setembro (eram ~2.772 pares).
  Esses frames são dado de `seco` para o Dataset A — vale copiar para o Mac em vez
  de deixar envelhecendo na Jetson.

---

# Ordem sugerida para a semana

| Quando | O que | Por quê nessa ordem |
|---|---|---|
| Hoje | Mandar B1/B2/B3 pro Guilherme | são bloqueios externos; perguntar cedo evita ficar parado |
| Hoje/amanhã | **A1 + A2** (`gps.py`, `captura.py`) | pré-requisito de toda sessão de outubro |
| Amanhã | **A3** (`modo_coleta`) | tem que estar de pé antes de apontar pra API real |
| Meio da semana | B1 + B4, teste ponta a ponta | já com A3 protegendo o dado local |
| Meio da semana | B2/B5/B6 conforme o Guilherme responder | dependem dele |
| Antes da 1ª chuva | **A4**: checklist impresso, trajeto escolhido | 5 minutos que valem uma sessão inteira |
| Se sobrar | Bloco C | nada bloqueia |

A tentação vai ser começar por B1, porque é a parte divertida e é o que "mostra
resultado". Mas se chover na quarta e o metadado estiver quebrado, a chuva não
volta — e a integração com a API volta, ela é só código.

# O que mandar de volta para o lado do ML

Para o `gerar_manifest.py` aproveitar o que o Bloco A produz, preciso de:

1. **Um JSON de exemplo** do metadado novo (schema 2), com fix e sem fix — para
   eu ajustar o parser antes da primeira sessão em vez de depois
2. **Confirmação de qual `modo_coleta` estava ativo** em cada sessão de outubro
   (se `false` em alguma, eu sei que faltam frames e de onde)
3. **Os `sem_chuva_pendente/` acumulados**, que são dado de `seco` para o gate
4. **A resposta do Guilherme sobre a cascata** (B3), que decide se o classificador
   de 3 classes é responsabilidade do backend ou volta pra borda
