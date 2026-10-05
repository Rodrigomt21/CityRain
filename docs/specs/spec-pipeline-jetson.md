# SPEC J — Pipeline completo da Jetson: captura → classificação → backend

> **Documento autocontido.** Tudo que é necessário para executar está aqui — não é preciso
> ler a conversa que o originou. Em caso de conflito entre esta spec e o estado real da
> placa, **pare e reporte a divergência** em vez de improvisar.
>
> Projeto: CityRain (TCC IMT). Convenções do repo: PEP 8, type hints em funções públicas,
> docstrings Google style, nomes de variáveis em inglês, comentários podem ser em português.
> Commits: `tipo: descrição` em português.
>
> Escrita em 2026-09-28 a partir de uma auditoria ao vivo da Jetson (`ssh jetson`,
> 192.168.0.154, hostname `yahboom`). Os números citados foram medidos nessa auditoria —
> ver **Apêndice A** para a evidência bruta de cada um.

## Responsáveis

Divisão atual confirmada por Rodrigo: Rodrigo e Guilherme — Jetson e modelos; Gabriel — backend; Paulo — frontend. As menções a dependências de backend abaixo se referem ao Gabriel.

## Objetivo

Deixar a Jetson capaz de fazer, sozinha e sem supervisão, um trajeto de coleta inteiro sem
perder dado, e entregar cada frame classificado ao backend de produção. O alvo tem duas
datas distintas e a spec é dividida por elas:

- **Fase 1 — Confiabilidade de campo.** Precisa estar pronta **antes da primeira chuva de
  outubro**. Sem ela, um evento de chuva coletado volta com buracos, e evento de chuva é o
  recurso mais escasso do projeto (ver `docs/plano-dataset.md`: existe **1** sessão
  rotulável hoje).
- **Fase 2 — Pipeline até o backend real.** Tira o sistema do `mock_backend.py` e o aponta
  para a API de produção. Parte depende de resposta do Gabriel (ver Apêndice C).
- **Fase 3 — Depois do modelo de intensidade treinado.** Troca o gate binário pelo modelo
  que estima intensidade, sem quebrar nada do que já funciona.

Uma regra atravessa as três fases: **a Jetson é o único lugar onde o frame de campo existe
até um 2xx do backend.** Toda decisão de projeto aqui protege essa cópia.

## Estado de partida (verificado em 2026-09-28)

| Componente | Estado |
|---|---|
| `captura.py` → `citycam.service` | funciona; 1 fps; grava par `.jpg`+`.json`; **sem `fsync`** |
| `gps.py` → `gps.service` | funciona; `A1`/`A2` aplicados no repo, **não deployados** |
| `gate.py` + `bestModel.onnx` | funciona; onnxruntime/CUDA ~95-100 ms/frame |
| `uploader.py` → `uploader.service` | roda **código antigo**; `backend_url` é placeholder |
| Registro no backend | **sem `api_key`** — bloqueado no Gabriel |
| Modelo de intensidade | **não existe ainda** (Fase 3 é preparatória) |
| Energia | **acendedor de cigarro** em carro **com start-stop**, sem bateria no caminho; 3 cortes na sessão de 23/09, rendimento de **24%** |
| Disco | raiz 14 GiB a 81%; **44,8 GiB não alocados** no mesmo SSD |

---

# FASE 1 — Confiabilidade de campo

## J1. Tornar o par jpg+json durável antes de anunciá-lo como pronto

### Contexto

Na sessão de 23/09, **63 de 305 frames (21%) voltaram com 0 byte** — jpg *e* json. O
mecanismo está provado: a energia caiu 3 vezes (registros `crash` no `wtmp`, sem nenhum
`shutdown system down`), e o boot seguinte registrou `EXT4-fs (sda1): 11 orphan inodes
deleted`. A raiz vive num **SSD USB 2.0**. Quando a energia cai, o *nome* do arquivo já foi
para o journal do ext4, mas os *dados* ainda estavam em página suja na RAM — resultado:
arquivo com nome final e conteúdo vazio.

Hoje o contrato interno é "a presença do `.json` significa que o par está completo"
(`captura.py:95`, `uploader.py:63`). Esse contrato é falso: o `.json` pode existir com o
`.jpg` ainda só em memória.

### Mudança

Em `captura.py`, escrever cada arquivo num `.tmp`, dar `fsync` no conteúdo, e só então
renomear para o nome final. O nome final passa a ser prova de durabilidade. Depois dos dois
renames, dar `fsync` no **diretório** — sem isso o próprio rename pode não ter durado.

```python
def _grava_duravel(caminho_final, escreve_em):
    """Escreve via .tmp + fsync + rename: o nome final só passa a existir
    quando o conteúdo já está fisicamente no disco.

    Isso existe porque a alimentação em campo é instável (ver J5): sem o
    fsync, um corte de energia deixa o arquivo com nome final e 0 byte, e o
    uploader trata esse par como válido. Mediu-se 21% de perda assim.
    """
    tmp = caminho_final + ".tmp"
    escreve_em(tmp)
    fd = os.open(tmp, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, caminho_final)


def _fsync_diretorio(caminho):
    """Torna os renames acima duráveis — o rename é metadado de diretório e
    também pode ser perdido num corte."""
    fd = os.open(caminho, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
```

No laço principal, a ordem passa a ser: grava jpg durável → grava json durável → `fsync` do
diretório. O `.jpg` continua sendo escrito antes do `.json`, porque a presença do `.json`
segue sendo o sinal de par completo para o `uploader.py`.

**Custo a medir, não presumir.** São 2 `fsync` de conteúdo + 1 de diretório por frame, num
SSD USB 2.0, a 1 fps. A folga existe (o laço dorme 1 s), mas tem de ser medida — se o tempo
de ciclo passar de 1 s, a taxa de captura cai e isso precisa ser uma decisão consciente, não
um efeito colateral.

### Aceite

- [x] `captura.py` grava jpg e json via `.tmp` + `fsync` + `os.replace`, e faz `fsync` do diretório após os dois
- [x] o jpg é codificado por `cv2.imencode(".jpg", frame)`, **nunca** por `cv2.imwrite` num caminho cuja extensão possa não ser de imagem — e há teste de regressão travando isso
- [x] caminho de produção exercitado contra o **OpenCV 3.2 real da Jetson**: jpg de 7.053 bytes gravado e relido como 640×480, sem `.tmp` residual, `fsync` de diretório OK, módulo importável sem efeito colateral
- [x] o laço captura `cv2.error` além de `IOError` — sem isso a exceção escapa, o processo morre e o `citycam.service` (`Restart=always`) entra em loop capturando zero frames
- [ ] nenhum arquivo com nome final (`frame_*.jpg` / `frame_*.json`) existe com 0 byte ao fim de uma sessão de 10 min
- [ ] **teste de sabotagem**: cortar a energia da placa no meio de uma captura em curso (5 repetições). Ao voltar, todo par com nome final é íntegro — jpg abre como JPEG válido e json faz `json.load` sem erro. Sobras admissíveis são apenas arquivos `.tmp`
- [ ] tempo de ciclo do laço medido **no SSD USB 2.0 da placa**, antes e depois, e registrado aqui. Medição em NVMe do Mac (0,12 → 0,23 ms) foi feita e **descartada como não representativa**: barreira de escrita sobre USB é ordens de grandeza mais lenta. Só fecha com hardware
- [x] arquivos `.tmp` remanescentes de um corte são ignorados pelo `uploader.py` (já são hoje, `uploader.py:74` — confirmar com teste)

## J2. A fila não pode morrer por causa de um par inválido

### Contexto

**Este é o item mais urgente da spec, e é um bug ativo, não uma melhoria.**

`uploader.py:244` chama `carrega_metadado(caminho_json)` fora de qualquer `try`. Num json de
0 byte, `json.load` levanta `JSONDecodeError`, que ninguém captura: o processo morre,
`Restart=always` o reinicia, `pares_pendentes()` devolve os pares em ordem cronológica e
entrega **o mesmo par inválido primeiro** — loop infinito, fila parada para sempre.

A quarentena por `TENTATIVAS_GATE_MAX` (`uploader.py:246`) **não protege** contra isso: ela
só é avaliada depois do `carrega_metadado`, que é justamente quem quebra.

Não é hipotético. Os 63 pares de 0 byte da sessão de 23/09 **estão neste momento em
`/home/jetson/frames`**, confirmado nesta auditoria:

```
-rw-r--r-- 1 jetson jetson 0  /home/jetson/frames/frame_20260923_100313_675.jpg
-rw-r--r-- 1 jetson jetson 0  /home/jetson/frames/frame_20260923_100313_675.json
$ python3 -c "import json; json.load(open('.../frame_20260923_100313_675.json'))"
JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

**A falha é latente, não imediata** — e é importante entender por quê, para não subestimá-la.
Verificado no journal em 2026-09-28: o serviço já roda o código com o gate, classificou o
primeiro par da fila como chuva e está preso tentando enviá-lo ao `backend_url` placeholder.
A falha de rede dispara `break` no par #1 a cada ciclo (`uploader.py:270`), então a execução
**nunca alcança** os pares de 0 byte, e `NRestarts` está em 0.

O crash-loop passa a acontecer no momento em que o `backend_url` apontar para um backend que
responde: a fila drena os pares válidos e para no primeiro par vazio. Isto é, **o J2 é
pré-requisito estrito do J13** (apontar para produção), e não uma limpeza opcional. O J1
impede que novos pares assim nasçam; o J2 lida com os 63 que já existem e com qualquer
corrupção futura.

### Mudança

Uma função de validação antes de qualquer processamento, e quarentena para quem falhar:

```python
PASTA_PAR_INVALIDO_PADRAO = "/home/jetson/frames/par_invalido"

def par_invalido(caminho_jpg, caminho_json):
    """Devolve o motivo (str) se o par não é utilizável, ou None se está ok.

    Um par inválido não é erro transitório: nenhum retry conserta um jpg de
    0 byte. Precisa sair da frente da fila, senão trava tudo atrás dele —
    pares_pendentes() sempre devolve o mais antigo primeiro.
    """
    if os.path.getsize(caminho_jpg) == 0:
        return "jpg de 0 byte"
    if os.path.getsize(caminho_json) == 0:
        return "json de 0 byte"
    with open(caminho_jpg, "rb") as f:
        if f.read(3) != b"\xff\xd8\xff":
            return "jpg sem magic bytes de JPEG"
    try:
        with open(caminho_json) as f:
            json.load(f)
    except (ValueError, OSError) as e:
        return f"json ilegível: {e}"
    return None
```

No laço, antes do `carrega_metadado`: se `par_invalido(...)` devolver motivo, mover o par
para `pasta_par_invalido` e registrar o motivo num `.csv` de auditoria. **Nada é apagado** —
o par inválido continua sendo evidência de um corte de energia e alimenta a contagem de
perda por sessão (J6).

O `carrega_metadado` também passa a ficar dentro de `try`, como defesa em profundidade: a
validação pode passar e o arquivo ser corrompido entre a checagem e a leitura.

### Aceite

- [x] par com jpg de 0 byte, json de 0 byte, json truncado, ou jpg sem magic bytes vai para `frames/par_invalido/` com o motivo registrado
- [x] `uploader.py` processa a fila inteira até o fim **sem morrer**, com os 63 pares inválidos de 23/09 presentes na fila (teste sobre uma cópia da fila real, nunca sobre a original)
- [x] `carrega_metadado` envolvido em `try`; falha nele não derruba o processo
- [x] nenhum par é apagado pela validação — só movido
- [x] teste automatizado em `ml/tests/` cobrindo os 4 modos de invalidez
- [x] `uploader.py` corrigido copiado para a Jetson (md5 conferido) — **serviço não reiniciado**, o processo em memória só troca no próximo restart
- [ ] confirmado em campo: uma sessão real termina com a fila drenada e os inválidos em quarentena

## J3. Nunca apagar o único registro local de um frame de campo

### Contexto

`apaga_par()` (`uploader.py:219`) remove jpg e json após um 2xx. Isso foi decidido em
2026-07-29 para resolver o aperto de disco, e faz sentido em regime permanente — mas durante
uma **sessão de coleta** é perigoso: o frame de campo passa a existir só no servidor. Se o
backend responder 2xx e depois perder o dado, ou se o payload estiver com o schema errado e
o backend aceitar mesmo assim, o frame já não existe mais em lugar nenhum.

A rotulagem por estação (`F1.3`) lê exatamente esses arquivos locais. Apagá-los durante a
temporada de chuva é apagar a matéria-prima do dataset.

### Mudança

Campo novo `modo_coleta` no `cityrain_config.json` (padrão `false`, comportamento atual
preservado). Com `modo_coleta: true`, `apaga_par()` **move** para
`frames/enviados/AAAAMMDD/` em vez de remover. O uploader loga o modo no arranque, para que
o journal registre inequivocamente em que regime a sessão rodou.

Subpasta por dia porque a cópia para a máquina do Rodrigo é feita por sessão, e uma pasta
única com dezenas de milhares de arquivos é hostil para `rsync` e para inspeção.

### Aceite

- [x] `modo_coleta: true`: após um 2xx, o par aparece em `frames/enviados/AAAAMMDD/` e **não** em `frames/`
- [x] o `AAAAMMDD` é a data de **captura** (extraída do nome do arquivo), nunca a data do envio — verificado contra os 328 nomes reais da coleta, que se separaram nas 3 sessões corretas (1 / 22 / 305). Nome fora do padrão cai para a data de hoje **e avisa no log**
- [x] `modo_coleta: false`: comportamento atual preservado (apaga)
- [x] o modo em vigor aparece no log de arranque do uploader
- [x] `frames/enviados/` é ignorado por `pares_pendentes()` (hoje `os.listdir` não é recursivo — confirmar com teste, não por leitura)
- [x] checklist de fim de sessão documentado (abaixo)
- [ ] `uploader.py` com o J3 copiado para a Jetson e `modo_coleta: true` no config da placa — **pendente de decisão**, porque ativar em fila com 1.713 pares muda o comportamento de uma sessão em curso

### Checklist de fim de sessão de coleta (`modo_coleta: true`)

1. Confirmar no `journalctl -u uploader.service` que a sessão arrancou com `modo_coleta=true` e que a fila principal (`~/frames`, nível superior) está drenando.
2. Copiar a pasta do dia: `rsync -av --progress jetson:/home/jetson/frames/enviados/AAAAMMDD/ ./frames_sessao_AAAAMMDD/`
3. Conferir a integridade: contagem de arquivos origem × destino, e checksum por amostra.
4. **Só depois** de confirmar a cópia íntegra, apagar `frames/enviados/AAAAMMDD/` na placa. Nunca automatizado.
5. Nunca apagar a subpasta do dia em andamento, nem qualquer pasta sem confirmação explícita de cópia segura.

## J4. Resolver o orçamento de disco com o espaço que já existe

### Contexto

A raiz (`/dev/sda1`) tem 14 GiB, está **81% usada, 2,6 GiB livres**. A captura a 1 fps
consome ~6,1 GiB/dia (medido em 2026-07-21; ~80 KB/frame medido agora). Com `modo_coleta:
true` (J3), que para de apagar, cabem ~8 sessões de uma hora antes de encher — insuficiente
para a temporada de outubro a novembro.

Mas o aperto é artificial. O SSD tem 59,5 GiB e a última partição termina no setor
30.777.311 de 124.735.488: **~44,8 GiB não alocados**. O layout de 17 partições é o clone
padrão da NVIDIA, que só usou a primeira faixa do disco.

Há ainda um segundo ponto: hoje os frames vivem na **partição raiz**. Encher a raiz não
enche "a pasta de frames", enche o sistema operacional — risco de corrupção muito pior que
perder captura.

### Mudança

Criar uma partição nova no espaço livre, formatar em ext4, montar em `/home/jetson/frames`
via `/etc/fstab` (com `nofail`, para que a placa ainda dê boot se o disco falhar). Isso
resolve o orçamento **e** isola a raiz do crescimento da coleta.

Ordem obrigatória, porque a operação é destrutiva se feita errada:

1. Copiar `frames/` inteiro para a máquina do Rodrigo e conferir por checksum **antes** de tocar no particionamento
2. Criar a partição apenas no espaço livre após o setor 30.777.311 — **nunca** redimensionar `sda1` nem as partições de 2 a 17 (são o layout de boot da NVIDIA)
3. Formatar, montar em ponto temporário, copiar o conteúdo atual de `frames/`, conferir
4. Só então ajustar o `fstab` e reiniciar

Requer `sudo` interativo; é o Rodrigo que roda (a sessão automatizada não tem polkit/D-Bus —
ver `CLAUDE.md`).

**Guarda de disco do `captura.py` (`ESPACO_MINIMO_MB = 500`) precisa ser revista** depois da
mudança: hoje ela mede `shutil.disk_usage(FRAMES_DIR)`, que passará a medir a partição nova.
500 MB num volume de 45 GiB é reserva pequena demais para dar tempo de reação.

### Aceite

- [ ] backup de `frames/` na máquina do Rodrigo, conferido por checksum, **antes** de qualquer alteração de partição
- [ ] partição nova criada só no espaço livre; `sda1` e as partições 2–17 intactas (comparar a tabela antes/depois)
- [ ] `/home/jetson/frames` montado na partição nova, com `nofail` no `fstab`
- [ ] placa reinicia duas vezes com o novo `fstab` e a montagem sobe sozinha nas duas
- [ ] teste de resiliência: com a linha do `fstab` apontando para um UUID inexistente, a placa **ainda dá boot** (prova que o `nofail` funciona)
- [ ] `ESPACO_MINIMO_MB` reavaliado para o novo tamanho e o valor justificado neste arquivo
- [ ] `df -h /home/jetson/frames` mostra ≥ 40 GiB disponíveis

## J5. Fechar o caminho de energia (a causa raiz dos cortes)

### Contexto

A causa dos cortes está identificada com evidência (Apêndice A): **perda de energia**, não
desligamento por software.

**A fonte em campo é o acendedor de cigarro** (confirmado pelo Rodrigo em 2026-09-28). Essa é
a pior opção possível para esta aplicação, por três razões independentes que se somam:

1. **Retenção mecânica por mola.** O plugue do acendedor é preso por pressão lateral, não por
   rosca ou trava. Vibração faz o contato abrir e fechar — é a causa clássica de corte
   intermitente em instalação automotiva, e explica diretamente por que só acontece no carro
2. **O carro tem start-stop** (confirmado pelo Rodrigo em 2026-09-28), e isso é a causa
   nomeada. A cada parada o motor desliga e religa; o religamento afunda o trilho de 12 V
   (o motor de arranque puxa 100–200 A) e, em muitos carros, o circuito ACC é inclusive
   desenergizado. Deixa de ser um evento único da viagem e passa a acontecer **em cada
   semáforo**. Numa manhã de chuva em trânsito de São Paulo, são dezenas de eventos —
   explica os três cortes espaçados ao longo de 17 minutos melhor que vibração pura
3. **Os adaptadores 12 V→5 V de acendedor entregam tipicamente 1–2,4 A.** A Nano em MAXN, com
   SSD USB (que é a raiz do sistema), dois hubs, câmera e dongle WiFi, pede da ordem de
   3–4 A. A fonte está subdimensionada mesmo sem nenhum problema de contato

Some-se a isso que a placa está em **MAXN (10 W)** — o modo alto; só existem `MAXN` e `5W`
nesta imagem.

**Consequência de projeto:** trocar o conector na placa (micro-USB → barril) *não resolve*,
porque o problema é a montante. Enquanto a energia vier do acendedor sem buffer, o corte
continua possível.

### Mudança

Em ordem de robustez. O item 2 é o que de fato fecha o problema e, com start-stop
confirmado, **não é opcional** — os outros apenas reduzem probabilidade.

1. **`sudo nvpmodel -m 1`** (modo 5W). Corta o pico do SoC pela metade e dá margem à fonte
   fraca. Grátis, reversível, imediato. Requer `sudo` do Rodrigo
2. **Obrigatório — bateria no caminho, não só uma fonte melhor.** Power bank com **pass-through charging**
   alimentando a placa enquanto é carregado pelo acendedor: a bateria absorve o corte da
   partida e a perda de contato por vibração, porque a placa nunca depende do trilho do carro
   em tempo real. É o equivalente a um UPS e é o único item que ataca as três causas de uma
   vez. Requisitos a conferir na compra: saída capaz de **5 V/3 A ou mais** e pass-through
   real (muitos modelos cortam a saída enquanto carregam — isso precisa ser testado, não
   presumido pelo anúncio)
3. **Alimentar pelo jack de barril** (5,5×2,1 mm, centro positivo) com o **jumper J48
   assentado**, em vez de micro-USB, que satura em ~2 A
4. **Alternativa ao item 2, eletricamente melhor e mais trabalhosa:** conversor DC-DC
   12 V→5 V de ≥ 5 A ligado direto na caixa de fusíveis com fusível próprio, mais capacitor de
   bulk ou módulo supercapacitor. Evita o acendedor por completo
5. **Alívio de tração** no plugue e reassentamento do J48. Paliativo, não substitui o item 2

O item 1 muda a performance do gate e **isso precisa ser remedido**: os números de
referência atuais (onnxruntime/CUDA ~95-100 ms/frame, CPU ~302 ms) foram medidos em MAXN.

### Aceite

- [ ] `nvpmodel -q` reporta `5W`, e **continua reportando após reboot**
- [ ] latência do gate remedida em 5W e registrada neste arquivo, ao lado do número de MAXN
- [ ] se a latência em 5W passar de 1.000 ms/frame, decisão explícita registrada: aceitar fila crescente, amostrar, ou voltar a MAXN com alimentação reforçada
- [ ] pass-through do power bank **testado na bancada**: com a placa ligada nele e a carga sendo conectada e desconectada 10 vezes, nenhum reboot e nenhum `crash` no `wtmp`
- [ ] fonte usada na próxima saída documentada: conector, tensão, corrente nominal, e se há bateria no caminho
- [ ] sessão de campo de ≥ 40 min **sem nenhum registro `crash` no `wtmp`** e sem nenhum `orphan inode` no boot seguinte — este é o aceite que de fato fecha o J5
- [ ] a mesma sessão com ≥ 5 ciclos de start-stop (paradas com o motor religando) sem perda de frame — o carro **tem** start-stop, então este aceite é obrigatório

## J6. Saber, no boot seguinte, o que aconteceu na sessão anterior

### Contexto

Hoje a diferença entre "a energia caiu" e "alguém apertou o botão" só foi descoberta
reconstruindo padrões de arquivos de 0 byte e cruzando com `wtmp` — trabalho de arqueologia
que não escala para uma temporada de coleta. Sem RTC, ainda por cima, os timestamps do
journal são pouco confiáveis até o NTP sincronizar.

A informação necessária é barata e existe: desligamento por software grava `shutdown system
down` no `wtmp` e desmonta limpo; corte de energia deixa `crash` e `orphan inodes`.

### Mudança

Um serviço `sessao.service` (`Type=oneshot`, `RemainAfterExit=yes`) que:

- no arranque, grava uma linha em `frames/sessao/boots.csv` com: hora do sistema, hora do
  GPS (`hora_rmc_utc`, quando houver — ver J7), se o marcador da sessão anterior ainda
  existia (⇒ crash), e a contagem de `orphan inodes` do `dmesg` do boot
- cria o marcador `frames/sessao/aberta`
- no `ExecStop`, remove o marcador — assim o marcador sobrevivente é, por si, a prova de que
  a sessão anterior não terminou de forma ordenada

Complementarmente, estender `verifica_teste_campo.py` (que já audita trajeto) para reportar
por sessão: nº de cortes, nº de pares inválidos em quarentena, e a **taxa de perda**. Na
sessão de 23/09 esse número teria sido `63/305 = 21%`, visível no mesmo dia em vez de cinco
dias depois.

### Aceite

- [ ] corte de energia real ⇒ próxima linha de `boots.csv` marcada como `crash`
- [ ] desligamento pelo botão ⇒ próxima linha marcada como `limpo`
- [x] `verifica_teste_campo.py` imprime, para uma sessão informada: frames escritos, válidos, pares inválidos, cortes detectados e taxa de perda
- [x] imprime também o **rendimento ponta a ponta** com destaque maior que a taxa de perda, mais tempo parado e cadência medida — porque taxa de perda baixa com rendimento terrível é um caso real (sessão que passa o tempo rebootando escreve poucos frames, quase todos íntegros)
- [x] há teste adversarial: sessão sintética com `taxa_perda == 0` e rendimento < 20% — prova que o rendimento denuncia o que a taxa de perda esconde
- [x] rodado retroativamente sobre a sessão de 23/09, reporta os 3 cortes e os 63 pares inválidos
- [x] o CSV é append-only e sobrevive a reboot

## J7. Tempo confiável sem RTC (`hora_rmc_utc`)

### Contexto

`capturado_em_utc` vem de `datetime.now()`, ou seja, do relógio do sistema — e esta Jetson
**não tem RTC utilizável** (`/dev/rtc*` existe, mas `hwclock -r` falha com "Cannot access
the Hardware Clock via any known method"; há `fake-hwclock` instalado como paliativo). Sem
NTP sincronizado antes da captura, o timestamp sai errado **e não há como saber depois que
saiu errado**. Foi isso que inutilizou as sessões de maio (19.037 frames que não casam com
estação nenhuma).

O receptor NEO-6M recebe a hora da constelação na sentença RMC e o `gps.py` já faz o parse
dela — apenas descarta a hora.

### Estado

**Já implementado no repo, ainda não deployado nem testado.** `gps.py` grava
`hora_rmc_utc` no braço do RMC quando `status == "A"`; `captura.py` subiu o schema de 1 para
2. Verificado que `datetime.combine(..., tzinfo=...)` funciona no Python 3.6.9 da placa e
que a versão de `pynmea2` é 1.19.0 tanto na placa quanto no venv do repo.

**Bug encontrado na auditoria (2026-09-28) e corrigido.** O braço do GGA em
`processa_linha()` mutava `estado["fix"]` e `estado["satelites"]` **antes** de converter
`horizontal_dil` para float. Um receptor não conforme entregando HDOP não numérico (com
checksum válido — exatamente o cenário que o `except (ValueError, TypeError)` existe para
cobrir) deixava `fix`/`satelites` novos com `latitude`/`longitude`/`ultimo_fix_em` atrasados:
um estado que **nunca existiu no receptor**, persistindo em memória até a próxima sentença
boa. Isso viola o requisito de que sentença malformada não corrompe o estado acumulado.
Corrigido convertendo todos os campos para locais antes de commitar em `estado` — ou a
sentença inteira é aplicada, ou nada dela é. O bug foi provado experimentalmente (revertendo
a correção, o teste de regressão falha com `satelites: 5 != 8`).

### Aceite

- [x] `ml/tests/test_gps.py` cobre: RMC com `status="A"` preenche; `status="V"` mantém `null`; sentença malformada não derruba
- [ ] json novo tem `gps.hora_rmc_utc` preenchido com fix, `null` sem fix
- [ ] bancada com NTP ok: `|capturado_em_utc − gps.hora_rmc_utc| < 2 s`
- [ ] **teste de sabotagem**: com Wi-Fi desligado e `sudo date -s "2020-01-01"`, o `hora_rmc_utc` continua correto e a divergência aparece entre os dois campos
- [ ] **deployado na Jetson**, não só commitado

## J8. Idade da posição (`ultimo_fix_em`)

### Contexto

Quando o fix cai, `gps.py` faz `fix = False` mas **mantém** `latitude`/`longitude` do último
fix — útil, mas quem lê o metadado não sabe se a coordenada é de 2 segundos ou de 20 minutos
atrás. O `atualizado_em` não serve: é atualizado a cada sentença NMEA, inclusive as que
reportam ausência de fix.

Isso não é teórico: nos frames novos trazidos de 23/09, há json com `capturado_em_utc` de
`2026-09-23T12:49` e `gps.atualizado_em` de `2026-09-16` — **sete dias de defasagem**, sem
nenhum campo que denuncie o fato.

Com `ultimo_fix_em`, a rotulagem pode aproveitar frames de fix recente: a 40 km/h, 5
segundos são ~55 m, muito abaixo do raio de 2 km da estação. É assim que se recupera parte
dos frames hoje descartados, **sem coletar nada novo**.

### Estado

**Já implementado no repo, ainda não deployado nem testado.** `gps.py` grava
`ultimo_fix_em` no braço do GGA quando há fix. O trecho que degrada o fix por silêncio
(`SILENCIO_MAX_S`) e o `except serial.SerialException` **não limpam** o campo — o valor
antigo é justamente o registro de quão velha a posição é.

### Aceite

- [x] com fix, `ultimo_fix_em` avança junto com o GGA
- [ ] arrancando a antena: `fix` vira `False`, `latitude`/`longitude` seguem preenchidos, `ultimo_fix_em` **congela** no último fix bom
- [ ] religando a antena, `ultimo_fix_em` volta a avançar
- [x] teste automatizado cobrindo os três casos acima com sentenças NMEA sintéticas
- [ ] o script de rotulagem (`F1.3`, `ml/scripts/rotulagem/gerar_manifest.py`) passa a considerar `ultimo_fix_em` como critério de idade máxima da posição, com o limite configurável — **é o item que recupera parte dos 1.703 frames hoje descartados sem coletar nada novo**
- [ ] **deployado na Jetson**

## J9. Botão de desligar: o pull-up que não existe

### Contexto

`botao_desliga.py:8` chama `GPIO.setup(inPin, GPIO.IN, pull_up_down=GPIO.PUD_UP)`. A
biblioteca **ignora esse parâmetro** — está no código dela, com aviso explícito:
`warnings.warn("Jetson.GPIO ignores setup()'s pull_up_down parameter")`
(`/usr/lib/python3/dist-packages/Jetson/GPIO/gpio.py:370`).

Hoje isso não causa problema: o pino lê HIGH estável (**452 amostras em 5 s, zero
transições**), então a placa Yahboom fornece pull-up externo. Mas a proteção que o código
acredita ter não existe, e se um jumper solto desconectar justamente esse pull-up, o pino
flutua e falso disparo passa a ser possível — exatamente o cenário de vibração no carro.

A hipótese inicial de que o botão causava os desligamentos foi **descartada** pela evidência
do `wtmp` (Apêndice A). Mas a partir do J6 as duas falhas ficam distinguíveis para sempre:
botão deixa `shutdown system down` e desmonte limpo; energia deixa `crash` e `orphan
inodes`.

### Mudança

1. Remover o parâmetro enganoso e documentar no código que o pull-up é **externo e
   obrigatório**, com o valor medido
2. Antes de desligar, gravar uma linha em `frames/sessao/boots.csv` registrando que o
   shutdown foi por botão — assim um falso disparo fica auditável em vez de virar mistério
3. Confirmar por multímetro que o pull-up externo existe no ponto onde o jumper conecta (não
   só no pino do SoC), e registrar o valor. **É o que fecha ou não a sua hipótese**
4. Se não houver pull-up externo confiável no ponto do jumper: adicionar resistor de 10 kΩ
   para 3,3 V

### Aceite

- [ ] `pull_up_down` removido; comentário explica que o pull-up é externo, com o valor medido
- [ ] nenhum `warnings.warn` da Jetson.GPIO no journal ao subir o serviço
- [ ] shutdown por botão grava linha de auditoria antes de desligar
- [ ] pull-up externo verificado no ponto do jumper e o valor registrado neste arquivo
- [ ] desconectando o jumper do botão, a placa **não desliga** em 5 min de vibração simulada
- [ ] debounce de 2 s validado com pressão física real (pendência aberta desde 2026-07-29)

---

# FASE 2 — Pipeline até o backend real

## J10. Sair do placeholder: device registrado e credenciais reais

### Contexto

`cityrain_config.json` tem `backend_url: "http://127.0.0.1:8080/upload"` e `token: null`. O
backend real está de pé (`https://api-production-046f.up.railway.app`, `/health` e
`/health/db` OK), mas **todos os endpoints exigem `HTTPBearer`** — inclusive
`POST /api/v1/devices/`, que é como se obtém a `api_key` do device. Ou seja: é preciso um
token admin do Gabriel só para conseguir a credencial da placa. A `api_key` aparece **uma
única vez**, na resposta de criação.

Bloqueio externo. O pedido formal já está escrito em `MUDANCAS_NECESSARIAS_BACKEND.md`.

### Mudança

Registrar o device (`name`, `hw_model: "jetson_nano"` — não `jetson_xavier`, que é só o
exemplo do schema), guardar a `api_key` em `cityrain_config.json`, que **permanece fora do
git**. Confirmar que o `.gitignore` cobre o arquivo antes de escrever segredo nele.

**Achado de segurança (2026-09-28), para levar ao Gabriel:** `GET /api/v1/captures/` e
`GET /api/v1/stats/geo` respondem **HTTP 200 sem autenticação nenhuma**, embora o `openapi.json`
declare `HTTPBearer` neles. Hoje não expõem nada porque o banco está vazio, mas a partir da
primeira coleta essas rotas devolvem publicamente as capturas com as coordenadas do trajeto.
As escritas estão protegidas (`POST /api/v1/ingest` sem token → 403), e a chave de device
corretamente **não** é admin (`GET /api/v1/devices/` com ela → 401).

### Aceite

- [x] `cityrain_config.json` confirmado fora do git **antes** de receber a `api_key` — estava **rastreado**; desrastreado com `git rm --cached`, coberto pelo `.gitignore`, e `cityrain_config.example.json` versionado no lugar
- [x] device registrado (`id=2`, `name=jetson-nano-01`, 2026-09-28); `api_key` persistida na placa e na cópia local, ambas com permissão `600` e conteúdo idêntico
- [ ] um par real sobe para a API de produção e volta 2xx
- [ ] o registro aparece no dashboard
- [ ] `backend_url` aponta para produção; nenhum `127.0.0.1` restante no config

## J11. O caso "seco" não tem para onde ir

### Contexto

`POST /api/v1/ingest` exige `image` no schema. Não existe endpoint para avisar "sem chuva"
sem subir foto — que é justamente o desenho pretendido (o gate existe para economizar
banda). Hoje `uploader.py` move o par para `frames/sem_chuva_pendente/` em vez de enviar ou
apagar: nada se perde, mas nada chega ao dashboard.

Há um segundo desencontro: `GET /api/v1/captures` e `GET /api/v1/stats/geo` usam enum de
**4 classes** (`seco/garoa/moderado/forte`), e o gate da Jetson é **binário**
(`chuva`/`seco`). A Jetson não tem como preencher `garoa`/`moderado`/`forte` hoje.

**Confirmado empiricamente em 2026-09-28 — não é mais leitura de schema, é resposta da API.**
Exercitei o caminho real do `uploader.py` (`classifica()` com o modelo desta placa, depois
`envia_par()`) contra produção, com um frame real da sessão de 23/09 (6 satélites, HDOP 1,43):

```
payload:  captured_at 2026-09-23T12:58:52.293992+00:00
          latitude -23.5503255  longitude -46.595389
          source_type jetson_nano
          weather_label "chuva"  confidence 0.9746221303939819

HTTP 400  {"detail":"weather_label deve ser um de: ['seco','garoa','moderado','forte']"}
```

Consequência dura: **hoje o `uploader.py` não consegue entregar um único frame de chuva à
produção.** Todo frame com chuva volta 400. O tratamento de 4xx do uploader está correto
(mantém na fila, loga com destaque, não descarta), então não há perda de dado — mas também
não há upload. O pipeline está funcionalmente parado nesse ponto.

E há uma ironia que orienta a saída provisória: **`seco` existe no enum e `chuva` não.** Ou
seja, o único rótulo que o gate produz e que a API aceitaria é justamente o que o
`uploader.py` nunca envia (ele desvia os "seco" para `sem_chuva_pendente/`).

**O que NÃO fazer, e é tentador:** mapear `chuva` → `garoa` para passar pela validação. O gate
é binário e não mede intensidade; `garoa` significa um intervalo de mm/h específico. Isso
seria fabricar intensidade e contaminar o banco de produção com rótulo inventado — a mesma
falha metodológica que o `docs/plano-dataset.md` rejeita ao proibir interpolação entre
estações. Se um dia o dashboard mostrar `garoa` para um frame que ninguém mediu, o número
deixa de significar qualquer coisa.

Ambos os pontos estão em `MUDANCAS_NECESSARIAS_BACKEND.md`, sem resposta.

### Mudança

Depende do Gabriel, e há duas saídas possíveis — a spec não escolhe por ele:

- **(a)** endpoint novo para "seco" sem imagem, ou `image` opcional no `/ingest`
- **(b)** a Jetson envia "seco" com imagem numa amostragem reduzida (ex.: 1 a cada N), o que
  custa banda mas não exige mudança no backend

**Plano B, se não houver resposta até o início da coleta:** manter o comportamento atual
(acumular em `sem_chuva_pendente/`) e tratar como dado local para o dataset. A coleta **não
pode ser bloqueada** por esta pendência — a chuva de outubro não espera o backend.

### Aceite

- [ ] decisão do Gabriel registrada em `MUDANCAS_NECESSARIAS_BACKEND.md` **ou** plano B explicitamente acionado, com data
- [ ] se (a): `move_para_pendente_seco()` substituída por chamada real e o caso "seco" aparece no dashboard
- [ ] se (b): taxa de amostragem configurável e documentada
- [ ] se plano B: `sem_chuva_pendente/` entra no checklist de cópia de fim de sessão (J3)
- [ ] em qualquer cenário: nenhum frame "seco" é apagado sem cópia confirmada

## J12. Limiar do gate e suavização temporal

### Contexto

`limiar_chuva` está em `0.5` e há decisão anterior de baixar para `0.3`. A justificativa é
assimetria de custo: **um falso negativo apaga dado de chuva** (o frame "seco" não é
enviado, e no regime antigo era apagado), enquanto um falso positivo só gasta banda. Com
recall de 96,1% e precisão de 99,5% no limiar 0,5, há margem para trocar precisão por
recall.

Há também uma preocupação já registrada e não implementada: o gate decide **por frame
isolado**, sem olhar a vizinhança temporal. Um frame que sai `sem_gota` por ruído pontual no
meio de uma sequência de chuva real se perde silenciosamente.

### Mudança

1. Baixar `limiar_chuva` para `0.3` via config (nunca hardcoded), e **medir** o efeito sobre
   um conjunto rotulado antes de fixar — o número 0,3 é hipótese, não resultado
2. Suavização temporal no espírito do debounce do botão: só tratar como "seco" após N frames
   consecutivos abaixo do limiar. Enquanto a decisão de onde suavizar (Jetson ou backend)
   estiver aberta com o Gabriel, implementar na Jetson é o caminho seguro — é a Jetson que
   descarta, e o que ela descarta ninguém recupera

### Aceite

- [ ] efeito do limiar 0,3 vs 0,5 medido sobre conjunto rotulado: recall, precisão e volume de upload, em tabela neste arquivo
- [ ] limiar vem do config; `grep -r "0\.5"` não encontra limiar hardcoded no caminho de decisão
- [ ] suavização com N configurável; `N=1` reproduz o comportamento atual (permite comparação justa)
- [ ] teste: sequência sintética `chuva, chuva, seco, chuva, chuva` com `N=3` **não** classifica o frame do meio como seco
- [ ] nenhum frame é descartado sem passar pela suavização

## J13. Teste de ponta a ponta contra a API real

### Contexto

O pipeline nunca rodou inteiro contra o backend de produção. O que já foi testado: gate
contra cópias isoladas de frames reais; uploader contra `mock_backend.py`. Nunca a cadeia
completa `captura → gate → upload → dashboard` com a fila real.

Aviso registrado em `CLAUDE.md` e que esta spec reitera: **reiniciar o `uploader.service`
dispara a reclassificação de toda a fila pendente e começa a mover os "secos" para fora de
`frames/`.** Com o motor ONNX isso custa ~5 min para ~2.800 pares — mas é uma ação com
efeito colateral em dado de campo, e só deve ser feita depois de J2 (senão a fila morre em
loop nos pares de 0 byte) e J3 (senão pares somem após 2xx).

### Mudança

Ensaio completo, em sequência: subir `citycam` + `gps` + `uploader` com config de produção,
capturar por 10 min com a câmera plugada, e verificar cada elo — frame nasce, gate
classifica, upload retorna 2xx, registro aparece no dashboard, par vai para `enviados/`.

### Aceite

- [ ] J1, J2 e J3 concluídos **antes** deste ensaio (pré-condição, não sugestão)
- [ ] ensaio de 10 min com os três serviços via systemd, não manualmente
- [ ] todo frame com chuva capturado no ensaio aparece no dashboard
- [ ] contagem fecha: `frames capturados = enviados + sem_chuva_pendente + par_invalido + fila restante`
- [ ] latência ponta a ponta medida (captura → visível no dashboard) e registrada
- [ ] teste de rede caindo no meio: desconectar a rede por 2 min; a fila retoma sozinha e nada se perde
- [ ] teste de corte de energia no meio do ensaio: ao voltar, a contagem ainda fecha

---

# FASE 3 — Depois do modelo de intensidade treinado

> Esta fase é **preparatória**. O modelo de intensidade não existe ainda — ver
> `docs/plano-dataset.md` (F3.2) e o gargalo de dados registrado ali: 478 frames rotulados,
> `zero moderada` e `zero forte`. A saída final do modelo **ainda é decisão aberta** (3 ou 4
> classes duras, ordinal, ou mm/h contínuo). O objetivo aqui é deixar a Jetson capaz de
> receber esse modelo sem retrabalho, **sem presumir qual das formas vencerá**.

## J14. Contrato de saída do modelo, versionado

### Contexto

Hoje `weather_label` é string livre (`"chuva"`/`"seco"`) e o backend usa enum de 4 classes.
Se o modelo passar a emitir mm/h contínuo ou uma classe ordinal, esse campo deixa de ser
suficiente — e trocá-lo sem versionamento quebra silenciosamente todo dado histórico já no
banco.

### Mudança

Declarar no metadado **qual modelo produziu qual saída**: identificador e versão do modelo,
a forma da saída (`binaria` / `classes` / `ordinal` / `mm_h`), o valor, e a confiança. O
schema interno já tem o campo `schema` (hoje `2`) para sinalizar mudança de formato — usar.

O backend precisa saber ler isso; entra no pedido ao Gabriel junto com o item 3 de
`MUDANCAS_NECESSARIAS_BACKEND.md` (formalizar `metadata` como schema tipado).

### Aceite

- [ ] metadado carrega identificador e versão do modelo, forma da saída, valor e confiança
- [ ] `schema` incrementado e a mudança documentada em `CONTRATO_API.md`
- [ ] frame antigo (schema 1 e 2) continua legível pelos scripts de rotulagem — **sem migração destrutiva**
- [ ] o backend aceita o formato novo, confirmado com o Gabriel, **antes** de qualquer envio em produção

## J15. Export ONNX, validação numérica e latência medida

### Contexto

O caminho já é conhecido e funcionou para o gate: `exportar_onnx.py` converteu
`bestModel.pth` → `bestModel.onnx` (opset 11, entrada fixa 1×3×384×384), validado bit a bit
contra o `.pth` no mesmo frame (probabilidade idêntica, 0.99665665...). O motivo de não usar
torch na placa está documentado: o wheel instalado tem kernels CUDA `sm_62`/`sm_72` e esta
GPU é Tegra X1, `sm_53`.

A lição a repetir é a da validação numérica: **exportar não é o mesmo que exportar certo**.

### Mudança

Para o modelo novo: exportar, validar numericamente contra o original em um conjunto de
frames (não em um só), e medir latência na placa **no modo de energia que a coleta vai
usar** (5W, se J5 for adotado).

### Aceite

- [ ] `.onnx` gerado com opset e shape de entrada documentados
- [ ] saída do `.onnx` conferida contra o original em ≥ 50 frames; diferença máxima registrada
- [ ] latência medida na placa em 5W e em MAXN, com warm-up separado do regime permanente
- [ ] decisão registrada: se a latência não couber no orçamento, o que muda (amostragem, modelo menor, ou classificação fora da placa)
- [ ] ONNX Runtime não cai silenciosamente para CPU — o provider em uso é logado no arranque

## J16. Substituir o gate binário pelo modelo de intensidade

### Contexto

O gate binário existe para economizar banda: decide se o frame sobe. O modelo de intensidade
responde outra pergunta — *quanta* chuva. Não são substitutos automáticos: se o de
intensidade for mais lento ou menos confiável em `seco`, pode fazer sentido manter os dois
em cascata (gate decide enviar, intensidade rotula).

Decidir isso **com número**, não por elegância de arquitetura.

### Mudança

Manter a interface de `gate.py` (recebe caminho de jpg + config, devolve dicionário) para
que a troca seja de implementação, não de arquitetura. Permitir, via config, três regimes:
só gate, só intensidade, ou cascata. Medir os três.

### Aceite

- [ ] os três regimes selecionáveis por config, sem alterar código
- [ ] tabela comparando os três: recall de chuva, latência por frame, volume de upload
- [ ] regime escolhido justificado pelos números, registrado neste arquivo
- [ ] fallback: se o modelo de intensidade falhar ao carregar, o sistema **degrada para o gate** em vez de parar de enviar
- [ ] teste do fallback com o arquivo do modelo ausente e com o arquivo corrompido

## J17. Cascata final e o que chega ao dashboard

### Contexto

Fechar o laço: o dashboard usa agregação H3 e enum de 4 classes. O que a Jetson envia tem de
ser inteligível para ele, e a conversão de uma saída ordinal ou contínua para a classe do
dashboard é **decisão de relatório** — os cortes (2,5 e 10 mm/h) podem mudar sem retreinar o
modelo, e por isso não devem ser assados na placa.

### Mudança

A Jetson envia a saída crua do modelo (mais a classe derivada, por conveniência). Os cortes
vivem em config, versionados junto do modelo. Se o dashboard precisar mudar um limiar, não é
preciso tocar na placa.

### Aceite

- [ ] a Jetson envia a saída crua **e** a classe derivada, com os cortes usados declarados no metadado
- [ ] mudar um corte no config altera a classe derivada sem reexportar o modelo
- [ ] dashboard exibe a classe corretamente para os quatro valores do enum
- [ ] um frame de cada classe percorre o caminho completo e aparece no dashboard
- [ ] `CONTRATO_API.md` atualizado e conferido com o Gabriel

---

# Apêndice A — Evidência medida em 2026-09-28

Auditoria ao vivo por `ssh jetson`. Os números abaixo sustentam as decisões da spec.

**Perda de dados na sessão de 23/09 (09:49–10:06, 305 frames):**

| Bloco | Frames | Vazios | Terminou em |
|---|---:|---:|---|
| 1 | 78 | 16 | corte de 503 s |
| 2 | 83 | 18 | corte de 135 s |
| 3 | 81 | 21 | corte de 106 s |
| 4 | 63 | 8 | fim da sessão |

Total: **63 de 305 frames escritos saíram vazios (20,7%)**, em pares jpg+json ambos com
0 byte.

Mas esse número subestima o prejuízo, porque ignora o tempo em que a placa esteve rebootando.
Contabilizando a sessão inteira (09:49:28,718 → 10:06:43,856 = 1.035 s):

| Medida | Valor |
|---|---:|
| Duração da sessão | 1.035 s (17,3 min) |
| Tempo parado (cortes + reboots de ~44 s) | **744 s — 72% da sessão** |
| Tempo capturando de fato | 291 s |
| Frames possíveis sem nenhum corte (a ~1,02 s/frame) | ~1.015 |
| Frames escritos | 305 |
| Frames válidos | **242** |
| **Rendimento ponta a ponta** | **23,8%** |

Ou seja: a sessão entregou **um quarto** do que deveria. É este o número a citar, não os 21%.

**Causa — perda de energia, não desligamento por software:**

- `wtmp` de 23/09 (no carro): três registros `crash`, **nenhum** `shutdown system down`
- `wtmp` de 15/09 (na bancada, botão): três `shutdown system down`, desmonte limpo
- boot seguinte: `EXT4-fs (sda1): 11 orphan inodes deleted` / `recovery complete`
- no bloco 3, 21 frames vazios consecutivos com a cadência de 1 fps **intacta**, recuperando
  sozinho depois — nenhum desligamento por software produz isso
- raiz em `/dev/sda1`, disco **USB** (`lsblk TRAN=usb`), `Attached SCSI removable disk`

**Configuração de energia:** fonte em campo = **acendedor de cigarro** (informado pelo Rodrigo).
`nvpmodel -q` → `MAXN`; modos disponíveis apenas `MAXN` e `5W`.
Temperaturas normais (CPU 39 °C, PMIC 50 °C) — não é throttling térmico.

**Botão (GPIO BOARD 13 = `gpio14`):** `direction=in`, valor **HIGH em 452/452 amostras em
5 s, zero transições**. `Jetson.GPIO` **ignora** `pull_up_down` (aviso explícito na própria
biblioteca, `gpio.py:370`) ⇒ o pull-up observado é externo.

**Disco:** `sda` = 63.864.569.856 B (59,5 GiB); `sda1` (raiz) = 15.032.385.536 B (14 GiB),
81% usada, 2,6 GiB livres. Última partição (`sda17`) termina no setor 30.777.311 de
124.735.488 ⇒ **~44,8 GiB não alocados**. O eMMC antigo (`mmcblk0p1`, montado em
`/media/jetson/EMMC`) tem erro de filesystem: `mounting fs with errors, running e2fsck is
recommended`, contador em 2 erros.

**Ambiente:** Python 3.6.9, `pynmea2` 1.19.0, L4T R32.7.6 / Ubuntu 18.04.6, kernel
4.9.299-tegra. `hwclock -r` falha ⇒ sem RTC utilizável; `fake-hwclock` instalado.

**Fila atual:** 1.713 pares em `/home/jetson/frames` (05/09 a 23/09), nunca enviados porque
`backend_url` é placeholder. Desses, 1.385 já estavam copiados em
`ml/data/raw/imt_coleta/cityrain_frames3`; os 328 restantes foram trazidos nesta auditoria
para `cityrain_frames4` (184 com `fix: true`, 81 sem fix, 63 pares vazios).

# Apêndice B — Ordem de execução

A ordem importa: alguns itens são pré-condição de outros, e dois deles são destrutivos se
feitos fora de ordem.

1. **J2** — antes de qualquer reinício do `uploader.service`, senão a fila morre em loop
2. **J1** — para parar de gerar pares inválidos novos
3. **J4** — antes de ativar `modo_coleta`, senão o disco enche; requer backup antes
4. **J3** — depende do J4
5. **J7, J8** — já implementados; falta teste e deploy
6. **J5, J6, J9** — hardware e diagnóstico; J5 tem o aceite mais longo (sessão real sem corte)
7. **J10 → J11 → J12 → J13** — Fase 2, na ordem; J13 exige J1, J2 e J3 prontos
8. **J14 → J17** — Fase 3, só depois de existir modelo treinado

**Mínimo para ir a campo em outubro:** J1, J2, J3, J4, J7, J8 e o item 1 do J5
(`nvpmodel -m 1`). Sem esses, uma manhã de chuva volta com buracos e não é repetível.

# Apêndice C — O que depende de terceiros

| Item | Depende de | Bloqueia |
|---|---|---|
| Token admin + `api_key` do device | Gabriel | J10, J13 |
| Endpoint para "seco" sem imagem | Gabriel | J11 (tem plano B) |
| Quem preenche `garoa`/`moderado`/`forte` | Gabriel | J11, J17 |
| `metadata` como schema tipado | Gabriel | J14 |
| `sudo` na placa (`nvpmodel`, `fstab`, partição, apt) | Rodrigo | J4, J5 |
| Fonte 5 V/4 A, buffer, alívio de tração | compra/montagem | J5 |
| Modelo de intensidade treinado | frente de ML (F3.2) | Fase 3 inteira |

O pedido formal ao Gabriel já está escrito em `MUDANCAS_NECESSARIAS_BACKEND.md`. Nenhum
item da Fase 1 depende dele — **a coleta de outubro não está bloqueada por terceiros.**
