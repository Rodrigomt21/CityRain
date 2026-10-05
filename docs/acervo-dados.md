# Acervo de Dados — CityRain

> Inventário levantado em 2026-09-05 sobre `~/Documents/faculdade7Semestre/TCC`.
> 27 GB em disco · **122.726 imagens** em 7 origens.

| | Imagens |
|---|---:|
| Coleta própria | 24.800 |
| Fontes públicas | 97.926 |
| **Total** | **122.726** |
| Rotuláveis por estação pluviométrica | 4.643 |
| Efetivamente rotuladas hoje | 0 |

---

## 1. Coleta própria — primeira geração (maio/2026)

Sem JSON, sem GPS, timestamps corrompidos.

| Pasta | Arquivos | Data no nome | Situação |
|---|---:|---|---|
| `code/classificador/imagens_brutas/` | 14.189 | 20/05 · 23/05 | timestamp corrompido |
| `framesSemNada/frames/` | 4.848 | 27/05 | 65 arquivos de 0 byte |
| `code/imagens_brutas/` | 14.187 | 20/05 · 23/05 | cópia redundante (903 MB) |

**Causa raiz dos timestamps** (já documentada em `code/classificador/.claude/CLAUDE.md`): a Jetson
Nano não tem RTC com bateria. Bootando offline assume hora errada. Três sessões foram gravadas com
carimbos colidindo em `20260520_22XX` e parte dos frames foi sobrescrita. A ordem alfabética dos
nomes não corresponde à ordem real de captura.

Os 65 arquivos vazios da `framesSemNada` estão espalhados entre 00:18:04 e 00:56:17, não em bloco.
Restam 4.783 legíveis.

## 2. Coleta própria — segunda geração (ago–set/2026)

Um `.json` por frame com `device_id`, `capturado_em_utc` e bloco `gps` completo.

| Pasta | Pares jpg+json | Sessão | Duração | GPS com fix |
|---|---:|---|---:|---|
| `cityrain_frames/` | 1.017 | 04/08, 08:12–08:29 | 17,3 min | 100% · 8,7 sat · HDOP 1,24 |
| `cityrain_frames2/` | 103 | 06/08, 22:31–22:33 | 1,7 min | 0% |
| `cityrain_frames2/` | 4.643 | 01/09, 07:32–08:51 | 79,5 min | 80,2% · 7,4 sat · HDOP 1,45 |

- Cadência de 1,02 s entre frames (mediana). Um único corte de 37 s em 01/09.
- Integridade: zero jpg sem json, zero json sem jpg.
- Bbox da sessão de 01/09: lat −23,5657..−23,5466 / lon −46,6593..−46,5880 (centro-sul de SP).
- Qualidade em 01/09: brilho mediano 107/255, 5 frames quase pretos, 7 muito borrados (0,26% de descarte).

**A sessão de 01/09 é o material mais valioso do acervo**: tem GPS, 80 minutos contínuos e transição
de chuva interna (gotas fortes às 07:32, para-brisa quase seco às 08:11, gotas esparsas às 08:47),
com câmera, montagem e trajeto constantes.

**Orientação:** as pastas `cityrain_frames*` gravam os frames rotacionados 180° — a câmera foi
reposicionada de propósito e a rotação é passo de pós-processamento. A `framesSemNada` está na
orientação normal. Normalizar **por pasta**, nunca globalmente.

## 3. Fontes públicas

| Acervo | Imagens | Rótulo disponível | Disco |
|---|---:|---|---:|
| YouTube + Pexels (54 vídeos, 17,8 h @ 1 fps) | 64.013 | tag por vídeo, manual | 1,6 GB (+6,7 GB de vídeo) |
| Guo & Breckon 2018 | 17.540 | binário gota/sem gota; 208 com bbox | 93 MB |
| RaindropsOnWindshield (Zenodo 4680442) | 16.373 | máscaras de segmentação + JSON | 14 GB |
| **Total** | **97.926** | **nenhum com mm/h** | 22,4 GB |

Pipeline em `ml/scripts/dataset_youtube/`: `captura_frames.py` + `links.txt` (55 URLs) gerou
`manifest.csv` com proveniência completa — 54 downloads OK, 1 falha por geoblock.

**Limitação metodológica:** nenhuma das 97.926 imagens tem intensidade em mm/h. Esse acervo serve
para pré-treino, diversidade visual e augmentação — não pode validar uma afirmação sobre quatro
níveis de intensidade.

## 4. Pipeline de rotulagem (`code/classificador/`)

| Passo | Saída | Volume | Estado |
|---|---|---:|---|
| 01 · dedup MD5 | `imagens_brutas_dedup/` | 14.151 | concluído |
| 02 · pré-rotulagem (Haiku 4.5) | `pre_rotulagem.json` | 14.151 | concluído |
| 02b · subsample estratificado | `imagens_subset/` | 2.100 | concluído |
| 03 · separação em baldes | `revisar/` + `imagens_brutas_manual/` | 2.075 | concluído |
| 04 · revisão humana | `dataset_bruto/` | — | **não iniciado** |
| 05 · consolidação | `dataset_bruto/{chuva,sem_chuva}` | 0 | bloqueado |
| 06 · split 70/15/15 com pHash | `cityrain_dataset/` | 0 | bloqueado |

Distribuição da pré-rotulagem automática (14.151 frames):

- `sem_chuva` — 11.842 (83,7%), confiança mediana 0,85
- `chuva` — 1.843 (13,0%), confiança mediana 0,85
- `duvidoso` — 466 (3,3%), confiança mediana 0,40

Razão 1:6,4 entre chuva e sem chuva — acima do limiar de alerta do próprio passo 5. Esses rótulos
foram **gerados por modelo, não medidos**: servem para triagem, não como ground truth do TCC.

O gargalo é humano: falta varrer os 1.975 frames dos baldes de alta confiança e rodar o rotulador
manual nos 100 duvidosos.

### Divergência de escopo a resolver

`CLAUDE.md` da raiz define classificação em **4 níveis** (`seco`/`garoa`/`moderada`/`forte`) com
rótulos derivados das estações públicas, como decisão fechada.
`code/classificador/.claude/CLAUDE.md` define classificação **binária** com rótulos visuais, também
como decisão de projeto. São dois trabalhos com dois ground truths diferentes; hoje só o segundo tem
dados prontos para andar.

---

## 5. Avaliação — o volume é suficiente?

**O volume bruto não é o problema.** 122.726 imagens é bastante em número absoluto; o irCNN, uma das
referências centrais do projeto, trabalhou com seis vídeos.

**A unidade estatística que importa não é o frame, é o evento de chuva independente.** A 1 fps, dois
frames consecutivos são quase a mesma imagem. Os 4.643 frames de 01/09 não são 4.643 amostras — são
*uma* chuva observada por oitenta minutos.

Contando eventos de chuva próprios com timestamp confiável **e** GPS — os dois requisitos para gerar
rótulo a partir do CGE-SP — o acervo tem **exatamente um**. As sessões de maio possivelmente contêm
chuva (13% pré-marcados assim), mas o relógio corrompido as torna impossíveis de casar com qualquer
estação; são utilizáveis apenas para o classificador binário com rótulo visual.

Isso colide com a regra que o próprio `ml/README.md` estabelece — *split por evento, não por frame*.
Com um evento não existe divisão possível: treino, validação e teste sairiam todos da mesma manhã, da
mesma rua, da mesma câmera. A acurácia resultante mediria memorização de cenário.

**As classes `moderada` e `forte` têm zero exemplo próprio hoje.** Temporal em São Paulo se concentra
entre outubro e março. Hoje é 05/09; o cronograma do pré-projeto prevê testes e validação para
agosto–setembro e entrega em novembro. A janela em que é fisicamente possível coletar chuva forte é
de **cerca de oito semanas** e começa depois do momento em que o cronograma esperava ter validação
pronta. É o calendário de São Paulo contra o calendário da faculdade.

### Recomendações

1. **Consertar o relógio da Jetson antes da próxima saída.** Sem timestamp confiável nenhum frame
   novo é rotulável pelo método do projeto — GPS sozinho não basta, o casamento com a estação é
   espaço *e* tempo. Pré-requisito, não melhoria.
2. **Definir a meta de coleta em eventos, não em frames.** Mirar 8–12 sessões chuvosas distintas
   entre outubro e novembro, variando horário, trajeto e intensidade. 30–60 min cada já sobra.
3. **Baixar a captura para 0,2 fps.** Um frame a cada 5 s carrega praticamente a mesma informação
   com 1/5 do armazenamento e muito menos redundância.
4. **Fechar o pipeline binário com o que já existe.** Entrega um resultado defensável em novembro
   independentemente de quanto chover. A taxa de correção sobre a pré-rotulagem do Haiku vira
   evidência metodológica, como o próprio pipeline já previu.
5. **Tratar as 4 classes como objetivo condicional.** Binário validado como resultado principal,
   4 níveis condicionados à coleta de out–nov.

---

## 6. Pendências técnicas consolidadas

| Item | Onde | Impacto |
|---|---|---|
| Relógio sem RTC corrompe timestamps | `ml/scripts/captura/` | **alto** — inviabiliza rótulo por estação |
| YouTube baixado em 360p | `captura_frames.py` | **alto** — 88,4% dos frames em 640×360 |
| Um vídeo é 58% do dataset público | `frames16/` (37.173 frames) | **alto** — vazamento no split |
| Pastas nomeadas pela linha de `links.txt` | `captura_frames.py` | médio — desalinha manifest se a lista mudar |
| 903 MB duplicados | `code/imagens_brutas/` | médio — risco de contagem dupla |
| 65 arquivos de 0 byte | `framesSemNada/frames/` | médio — quebra leitura em lote |
| 13 vídeos em formato retrato | `processed/youtube/` | médio — enquadramento não-dashcam |
| Orientação inconsistente entre pastas | `cityrain_frames*` vs `framesSemNada` | médio — normalizar por pasta |
| Retomada por existência de arquivo | `captura_frames.py` | latente — hoje nenhuma pasta parcial |

### Detalhe: o filtro de download do YouTube

`-f best[ext=mp4]/best` pega o stream progressivo do YouTube, que para em 360p (acima disso é DASH,
com faixas separadas). 14 dos 18 vídeos do YouTube vieram em 640×360, incluindo os três marcados
`4k` e o marcado `hd`.

| Resolução | Frames | % |
|---|---:|---:|
| 640×360 | 56.559 | 88,4% |
| 1920×1080 | 6.924 | 10,8% |
| resto | 530 | 0,8% |

Correção: `-f "bv*[height<=1080]+ba/b[height<=1080]/b"` com `--merge-output-format mp4`. Os vídeos já
baixados precisam ser rebaixados — `baixar_video()` pula quando o destino existe.

### Verificações feitas em 05/09/2026

- Os 54 vídeos do manifest batem com `n_frames ≈ duração × 1 fps` — nenhuma extração parcial.
- Nenhum `source_id` ou URL duplicada em `links.txt`.
- Pares jpg/json íntegros nas três pastas de coleta própria com metadado.
