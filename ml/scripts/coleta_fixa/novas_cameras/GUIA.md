# Kit de novas câmeras — guia passo a passo (Paulo e Moreno)

> **Objetivo:** achar câmeras **novas** (lives públicas com pluviômetro CEMADEN perto), coletar fotos delas
> **ao vivo** e **do passado** (DVR do YouTube, ~5 dias), baixar as leituras do pluviômetro com a **sua** conta
> e conferir quantas fotos ganham rótulo. O Guilherme continua com as 16 câmeras que já captura
> (`cameras_ja_capturadas.csv`); vocês somam câmeras novas.
>
> Antes de começar, leia o [CONTEXTO-TCC.md](CONTEXTO-TCC.md): ele explica **por que** cada regra existe.

## O que tem nesta pasta

**Os 3 que ficam rodando** (cada um no seu terminal):

| Script | O que faz | Passo |
|---|---|---|
| `ao_vivo.py` | **ao vivo**: 1 foto por câmera a cada 10 min | 6 |
| `retrospectiva.py` | **passado**: baixa o DVR do YouTube (~5 dias) em blocos de 30 min com pausa | 7 |
| `cemaden.py` | **pluviômetro**: leituras de 10 min do PED com a sua conta; `--previa` mostra os rótulos | 8–9 |

**Os 2 de apoio** (antes de coletar):

| Script | O que faz | Passo |
|---|---|---|
| `buscar_lives.py` | procura lives ao vivo no YouTube | 3 |
| `triagem.py` | confere se a câmera cumpre as regras e gera a lista de estações do PED | 4 |

**Documentos e modelos:**

| Arquivo | Para quê |
|---|---|
| `GUIA.md` | este guia |
| `CONTEXTO-TCC.md` | como a coleta vira rótulo, dataset e modelo do TCC (ler antes) |
| `cameras_ja_capturadas.csv` | câmeras que a equipe **já captura**, já **descartou** (com o motivo) e **pistas** livres |
| `exemplo_minhas_cameras.yaml` | modelo da sua config de câmeras |
| `env.example` | modelo do `ml/.env` (sua conta do CEMADEN) |
| `estacoes_com_defeito.txt` | estações que não devem ser usadas |
| `comum.py` | funções usadas pelos scripts (não precisa rodar) |

Todos os comandos são rodados **da raiz `CityRain/`**, com o venv ativo. Nos exemplos o nome é `paulo`:
troque pelo seu (`moreno`). O nome separa as pastas de cada um: **ninguém escreve na pasta do outro**.

| O quê | Onde fica | Vai para o Git? |
|---|---|---|
| sua config de câmeras | `ml/configs/coleta_fixa_novas_paulo.yaml` | pode (não tem segredo) |
| suas fotos, leituras, planos, logs | `ml/data/raw/novas_paulo/` | **não** (já está no `.gitignore`) |
| sua senha do CEMADEN | `ml/.env` | **NUNCA** |

---

## Passo 1 — Preparar o computador (uma vez, ~20 min)

**1.1 Código.** `git pull` na branch que tiver este kit (pergunte ao Guilherme qual).

**1.2 Python 3.11 + venv + pacotes.**

Mac/Linux:
```bash
python3.11 -m venv ml/.venv
source ml/.venv/bin/activate
python -m pip install -r ml/requirements-ci.txt yt-dlp
```

Windows (PowerShell):
```bash
py -3.11 -m venv ml\.venv
ml\.venv\Scripts\Activate.ps1
python -m pip install -r ml\requirements-ci.txt yt-dlp
```
Se o PowerShell bloquear o `Activate.ps1`, rode antes: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
**No Windows, rode também `$env:PYTHONUTF8 = "1"` em todo terminal novo** (senão os acentos dos arquivos quebram).

**1.3 ffmpeg** (tira a foto do vídeo). Mac: `brew install ffmpeg`. Windows: `winget install Gyan.FFmpeg`
(feche e abra o terminal depois). Conferir: `ffmpeg -version` e `yt-dlp --version`.

**1.4 Relógio do computador sincronizado — obrigatório.** O horário de cada foto ao vivo vem do relógio do PC,
e o rótulo depende desse horário. No PC do Guilherme o Windows estava **7 min adiantado** e foi preciso corrigir
888 fotos. Windows: Configurações → Hora e idioma → Data e hora → "Definir horário automaticamente" →
"Sincronizar agora". Para conferir, `w32tm /query /status` deve mostrar uma fonte de hora (ex.: `time.windows.com`).
Mac: Ajustes → Geral → Data e Hora → "Definir automaticamente".

**1.5 Não deixar o computador dormir** enquanto coleta: na tomada, tampa aberta, suspensão desligada.
Mac: rode os comandos longos com `caffeinate -i` na frente.

---

## Passo 2 — Sua conta do CEMADEN (PED)

1. Cadastre-se em **https://ped.cemaden.gov.br/cadastrarUsuario** (nome, e-mail, senha).
2. Copie o modelo para o lugar certo e preencha com **os seus** dados:
   - Mac/Linux: `cp ml/scripts/coleta_fixa/novas_cameras/env.example ml/.env`
   - Windows: `copy ml\scripts\coleta_fixa\novas_cameras\env.example ml\.env`
   - Edite `ml/.env`: `CEMADEN_EMAIL=seu@email` e `CEMADEN_SENHA=suasenha` (sem espaço, sem aspas).
3. Teste o login (não baixa nada):
```bash
python ml/scripts/coleta_fixa/novas_cameras/cemaden.py --nome paulo --teste
```
Tem de aparecer `Login ok (seu@email)`.

**Regras da conta:** o `ml/.env` nunca vai para o Git, para o grupo ou para pacote de dados. O PED limita
acessos por cadastro (erro **401**): o script para sozinho depois de 3 respostas 401 seguidas. **Não troque de
conta para contornar a cota**: espere e rode de novo mais tarde (o que já veio é pulado). Cada um usa a sua conta
para as estações das **suas** câmeras; o Guilherme já baixa as estações das câmeras dele.

---

## Passo 3 — Achar câmeras novas e confirmar o endereço

**3.1 Onde procurar.** O que decide se uma câmera serve é **ter pluviômetro CEMADEN reportando perto**. Comece
pelas regiões com rede densa (capital e interior de SP, litoral de SP e RJ, Serra do RJ, Sul, BH) e pelas
**pistas** da planilha `cameras_ja_capturadas.csv` (situação `PISTA`: passaram no pluviômetro, ninguém pegou).

**3.2 Buscar lives** (uma consulta por vez, com pausa — não aumente o ritmo):
```bash
python ml/scripts/coleta_fixa/novas_cameras/buscar_lives.py --nome paulo --cidade "Petrópolis" --cidade "Joinville"
python ml/scripts/coleta_fixa/novas_cameras/buscar_lives.py --nome paulo --canal https://www.youtube.com/@NOMEDOCANAL
```
Sai `ml/data/raw/novas_paulo/lives_encontradas.csv` com título, canal, link e os trechos da descrição que parecem
endereço. Canal que tem uma câmera boa costuma ter várias: vale listar as lives do canal (`--canal`).

**3.3 Descartar na hora** (já aconteceu com a equipe):

| Não serve | Por quê |
|---|---|
| já está em `cameras_ja_capturadas.csv` (capturando ou descartada) | duplicaria trabalho |
| perto de Balneário Camboriú (≤ 15 km) | BC é a câmera de **teste**; vizinha no treino vazaria o teste |
| câmera que gira, dá zoom ou tem "Preset" na tela | a cena muda; atrapalha o modelo e a referência seca |
| live que alterna várias câmeras ("carrossel") | não dá para saber qual câmera é cada foto |
| câmera residencial / "monitoramento privado" | privacidade |
| descrição que **proíbe** uso das imagens | não pode entrar num TCC |
| câmera "aberta" por falta de senha (Insecam, Shodan) | acesso não autorizado |

**3.4 Confirmar o endereço — a parte mais importante.** A posição (lat/lon) é gravada em **cada foto** no
momento da captura, e o rótulo sai do pluviômetro mais perto dessa posição. Posição errada = rótulo errado
(em Maresias o ponto estava 1,4 km fora). Formas que funcionaram:

| Evidência | Exemplo | Vale como verificada? |
|---|---|---|
| link do Google Maps na descrição da live | Marina Zeus (São Vicente) | **sim**: abra o link e copie a coordenada |
| endereço (rua e número, condomínio, hotel) na descrição | Maresias (Condomínio Ondas) | **sim**: procure no Google Maps |
| praça/marco citado + algo que aparece na imagem bate com o mapa | Miracema (igreja da praça) | **sim** |
| só a praia, mas **qualquer** ponto dela fica a ≤ 2 km da estação (ou com ≥ 3 a ≤ 5 km) | Perequê-Açu | sim, anotando isso na descrição |
| só o nome da cidade | Taboão, Guarapuava | **não**: não marque `true` |

Na dúvida, deixe `posicao_verificada: false`: a triagem **reprova** a câmera e você não gasta tempo coletando
algo que não vai entrar no treino. (O Guilherme tem câmeras nessa situação, Taboão e Guarapuava, e elas
ficaram travadas, com chuva forte e tudo.)

**3.5 Montar a sua config.** Copie o modelo e preencha uma entrada por câmera:
- Mac/Linux: `cp ml/scripts/coleta_fixa/novas_cameras/exemplo_minhas_cameras.yaml ml/configs/coleta_fixa_novas_paulo.yaml`
- Windows: `copy ml\scripts\coleta_fixa\novas_cameras\exemplo_minhas_cameras.yaml ml\configs\coleta_fixa_novas_paulo.yaml`

Troque `SEUNOME` no `destino` (`ml/data/raw/novas_paulo/frames`). Para cada câmera: `id`, `url`, `lat`, `lon`,
`descricao` (quem publica + endereço), `posicao_verificada`, `fonte_publica` (link da prova).

**3.6 Avise no grupo** quais câmeras você pegou (id + link), para o outro não pegar a mesma.

---

## Passo 4 — Triagem: a câmera cumpre as regras?

```bash
python ml/scripts/coleta_fixa/novas_cameras/triagem.py --nome paulo
```
Para cada câmera: já capturada? perto de BC? pluviômetro CEMADEN **reportando** a ≤ 2 km (ou ≥ 3 a ≤ 5 km)?
posição verificada com fonte? quanto choveu perto nos últimos 7 dias? a live tem DVR (passado)?
Sai `triagem.csv` e `estacoes_paulo.json` (as estações que você vai baixar do PED). **Ponha `ativa: false` nas
reprovadas.** Se o YouTube reclamar, rode com `--sem-dvr`.

---

## Passo 5 — Teste de uma rodada

```bash
python ml/scripts/coleta_fixa/novas_cameras/ao_vivo.py --nome paulo --uma-rodada
```
Abra uma foto de cada câmera em `ml/data/raw/novas_paulo/frames/<câmera>/` e o JSON ao lado:
- a imagem é a câmera certa, externa, sem tela de "offline"?
- se a câmera mostra relógio na imagem, ele bate com o `capturado_em_utc` do JSON (UTC = Brasília + 3 h)?
  Diferença de minutos = relógio do PC errado (volte ao passo 1.4).

## Passo 6 — AO VIVO (terminal 1, fica rodando)

```bash
python ml/scripts/coleta_fixa/novas_cameras/ao_vivo.py --nome paulo
```
(Mac: `caffeinate -i python ...`.) Deixe rodando; **não feche a janela**. 1 foto por câmera a cada 10 min.
Câmera que falha espera cada vez mais (até 30 min) antes de tentar de novo; "repetido (descartado)" = imagem
congelada, é normal. Ctrl+C encerra; para retomar, rode o mesmo comando.

## Passo 7 — RETROSPECTIVA (terminal 2, fica rodando até acabar)

O DVR guarda ~5 dias e **apaga o mais antigo a cada hora**: comece logo depois de ligar o ao vivo.
```bash
python ml/scripts/coleta_fixa/novas_cameras/retrospectiva.py --nome paulo --so-planejar   # opcional: só ver o plano
python ml/scripts/coleta_fixa/novas_cameras/retrospectiva.py --nome paulo
```
Em ciclos, sozinho: **planeja** (acha os buracos sem foto dentro do que o DVR alcança e marca as horas de chuva,
pelo mapa público ou pelas suas leituras do PED se já baixou), **baixa** por 30 min, **pausa** 30 min e
replaneja, até não sobrar buraco. Padrão: **1 foto a cada 10 min** — de minuto em minuto sai foto quase
repetida, e o que conta é o número de **eventos** de chuva, não de fotos.

**Para sozinho** se o YouTube pedir "confirme que não é um robô" — não use cookies, VPN ou outra rede para
contornar; espere algumas horas e rode de novo (continua de onde parou). Em 11/10, 5 downloads em paralelo
bloquearam o PC do Guilherme e derrubaram o coletor ao vivo dele por 2 h. Live sem DVR (ou que reinicia todo dia)
é abandonada sozinha: dela só vale o ao vivo.

## Passo 8 — CEMADEN (terminal 3, tenta a cada 30 min até completar)

```bash
python ml/scripts/coleta_fixa/novas_cameras/cemaden.py --nome paulo --dias 6 --repetir --previa
```
Baixa os últimos 6 dias **completos** das estações das suas câmeras (o dia de hoje só fecha amanhã) e, ao
terminar, mostra a prévia dos rótulos. Com `--repetir`, tenta de novo a cada 30 min até completar (cada
tentativa para no 3º erro 401 seguido). Não tem pressa como o DVR: o PED guarda o histórico.
Quando terminar, **rode de novo a retrospectiva** (passo 7): agora ela usa a chuva precisa do PED.
Volte a rodar o `cemaden.py` a cada 1–2 dias para os dias novos.

## Passo 9 — Prévia dos rótulos (quando quiser)

```bash
python ml/scripts/coleta_fixa/novas_cameras/cemaden.py --nome paulo --so-previa
python ml/scripts/coleta_fixa/novas_cameras/cemaden.py --nome paulo --so-previa --previa-5km
```
Mostra por câmera quantas fotos viraram seco/garoa/moderada/forte e em quantos **eventos**. É só uma prévia:
não mexe nos manifests oficiais. O `--previa-5km` mostra moderada/forte pelo consenso de 5 km, que só valem
depois da revisão visual.

## Passo 10 — Entregar os dados

1. Pare o coletor (Ctrl+C) para o pacote ficar fechado; religue depois se quiser.
2. Rode a prévia (passo 9) uma última vez.
3. Empacote a sua pasta **sem** o `.env`:
   - Mac/Linux: `tar -czf ../novas_paulo_AAAAMMDD.tar.gz ml/data/raw/novas_paulo ml/configs/coleta_fixa_novas_paulo.yaml`
     e `shasum -a 256 ../novas_paulo_AAAAMMDD.tar.gz > ../novas_paulo_AAAAMMDD.tar.gz.sha256`
   - Windows: `tar -czf ..\novas_paulo_AAAAMMDD.tar.gz ml\data\raw\novas_paulo ml\configs\coleta_fixa_novas_paulo.yaml`
     e `Get-FileHash ..\novas_paulo_AAAAMMDD.tar.gz -Algorithm SHA256`
4. Suba o `.tar.gz` **e** o `.sha256` no Drive da equipe, com um `RESUMO-ENTREGA.md` (modelo no
   `docs/GUIA-COLETA-EQUIPE.md`, seção 8): câmeras, período UTC, nº de fotos, dias do PED completos/pendentes,
   falhas, e o que a prévia deu.
5. Abra um PR só com a sua config (`ml/configs/coleta_fixa_novas_paulo.yaml`). **Nunca** imagens, `.env` ou tokens.

---

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| `yt-dlp não encontrado` | ative o venv (passo 1.2) |
| `ffmpeg` não encontrado | instale (passo 1.3) e abra um terminal novo |
| `Permission denied` do ffmpeg no Windows | use o `ao_vivo.py` deste kit, não o `coletor.py` direto |
| acentos estranhos / erro de `charmap` no Windows | `$env:PYTHONUTF8 = "1"` no terminal |
| "Sign in to confirm you're not a bot" | pare tudo que baixa do YouTube por algumas horas; o coletor ao vivo volta sozinho |
| "This video is not available" | a live caiu ou trocou de link: procure a live nova no canal (`buscar_lives.py --canal`) |
| CEMADEN 401 | cota do cadastro: o script para; rode de novo mais tarde. Não troque de conta |
| "Nenhum resultado" do CEMADEN | a estação não tem dado naquele dia: normal, é pulado nas próximas vezes |
| horário da foto ≠ relógio da imagem | relógio do PC (passo 1.4) |
| live que reinicia todo dia | não tem passado (DVR): só o coletor ao vivo serve. Use o link do canal `/live` na config |

## Resumo de comandos (troque `paulo` pelo seu nome)

Antes de coletar (apoio):
```bash
python ml/scripts/coleta_fixa/novas_cameras/cemaden.py --nome paulo --teste
python ml/scripts/coleta_fixa/novas_cameras/buscar_lives.py --nome paulo --cidade "Cidade"
python ml/scripts/coleta_fixa/novas_cameras/triagem.py --nome paulo
python ml/scripts/coleta_fixa/novas_cameras/ao_vivo.py --nome paulo --uma-rodada
```

Os 3 que ficam rodando (um terminal cada):
```bash
python ml/scripts/coleta_fixa/novas_cameras/ao_vivo.py --nome paulo
python ml/scripts/coleta_fixa/novas_cameras/retrospectiva.py --nome paulo
python ml/scripts/coleta_fixa/novas_cameras/cemaden.py --nome paulo --dias 6 --repetir --previa
```
