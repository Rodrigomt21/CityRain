# Contexto: como a coleta de fotos vira rótulo, dataset e modelo do TCC

> Para quem vai procurar e coletar câmeras novas. O passo a passo está no [GUIA.md](GUIA.md); aqui está o
> **porquê** de cada regra. Fontes no repo: `CLAUDE.md` (seção "ESTADO ATUAL"), `docs/specs/spec-camera-fixa.md`
> (regras CF1–CF5), `docs/PASSAGEM-camera-fixa.md`, `docs/GUIA-COLETA-EQUIPE.md`, `docs/GUIA-TREINO-EQUIPE.md`.
> Escrito em 13/10/2026 pelo Guilherme (com Claude).

## 1. O que o TCC precisa até 20/10

O CityRain classifica a chuva numa imagem de câmera em **4 classes**: `seco`, `garoa`, `moderada`, `forte`.
Em 08/10 o orientador alertou risco de reprovação por falta de dado real. A resposta da equipe foi um
**modelo só para câmera fixa** (lives públicas), treinado **só com dado real** e rotulado por **pluviômetro**:
nada de sintético, nada de "olhômetro".

| Classe | Intensidade (mm/h) |
|---|---|
| `seco` | 0, e nenhuma estação a ≤ 5 km com chuva em ±60 min |
| `garoa` | 0 < i ≤ 2,5 |
| `moderada` | 2,5 < i ≤ 10 |
| `forte` | > 10 |

## 2. O caminho de uma foto até o modelo

```
live do YouTube ──► foto JPG + JSON (horário UTC, posição da câmera)          ao_vivo.py / retrospectiva.py
                                   │
pluviômetro CEMADEN (PED, 10 min) ─┤                                            cemaden.py
                                   ▼
                    gerar_manifest.py: rótulo de cada foto                      regra CF3
                                   ▼
                    montar_splits_fixa.py: treino / validação / testes          regra CF4
                                   ▼
                    treino F0–F3 → escolha pelo critério CF5 → ONNX → backend → dashboard
```

**Como o rótulo é decidido (CF3)** — é isso que define se uma foto "vale":
1. Pega a estação **reportando a ≤ 2 km** da câmera e soma a chuva dela em **±15 min** do horário da foto → mm/h.
2. Se não há estação a ≤ 2 km: **consenso** de ≥ 3 estações a ≤ 5 km, todas na mesma classe. Discordou, sai.
3. **Zona morta** de ±15% em volta de 2,5 e 10 mm/h: foto na fronteira entre classes é descartada.
4. `seco` só com confirmação regional: nenhuma estação a ≤ 5 km com chuva em ±60 min.
5. Consenso a 5 km para moderada/forte (CF3.2) entra **só depois da revisão visual** (alguém olha painéis e
   exclui câmera tampada, congelada, tela offline).

Consequências práticas que vocês vão ver na prévia:
- **Uns 35–40% das fotos ganham rótulo**; o resto sai por falta de leitura perto daquele horário. Com tempo seco,
  as estações do CEMADEN mandam leitura **1 vez por hora**; com chuva, de 10 em 10 min. Por isso o seco perde
  mais fotos que a chuva. É normal.
- **Posição errada estraga o rótulo.** O horário e a posição gravados no JSON são o que liga a foto à estação.

## 3. Por que essas regras de escolha de câmera (CF1)

| Regra | Motivo |
|---|---|
| pluviômetro CEMADEN **reportando** a ≤ 2 km (ou ≥ 3 a ≤ 5 km) | sem isso a foto nunca ganha rótulo: é foto inútil |
| posição **verificada** com fonte pública | a rotulagem depende da distância câmera ↔ estação; a regra do projeto só aceita `true` com certeza |
| transmissão pública de propósito, sem proibição de uso | ética e direito de uso num TCC |
| câmera fixa (sem zoom/presets), uma câmera por live | o modelo F3 compara a foto com uma foto **seca da mesma cena**; se a cena muda, não funciona |
| longe de Balneário Camboriú | BC é a câmera de **teste B** ("câmera nunca vista"); vizinhas no treino veriam a mesma chuva |
| live com DVR | permite recuperar ~5 dias de passado (é de onde vem a maior parte da chuva) |

## 4. O que é "evento" e por que importa mais que "foto"

**Evento** = sequência de fotos da mesma câmera sem intervalo maior que 60 min (CF3.3). Splits e métricas são
**por evento**, e o treino usa no máximo **200 fotos por (evento, classe)** (CF4.1). Então 60 fotos de minuto em
minuto da mesma chuva valem como **1 evento**. Por isso o kit baixa **1 foto a cada 10 min**: mesma diversidade,
10× menos pedidos ao YouTube, nada de foto repetida.

**O que mais falta ao modelo é moderada e forte brasileira, em câmeras diferentes.** Hoje quase todo o `forte`
vem do dataset chinês irCNN; o risco nº 1 da spec é o modelo aprender "cena do irCNN ⇒ forte". Cada câmera
brasileira com um evento de forte ajuda a quebrar esse atalho. O `seco` também precisa existir em **toda**
câmera (meta CF4.2: ≥ 300 por câmera, de dia e de noite), senão a câmera vira atalho para a classe.

## 5. As datas (atenção)

| Data | O que significa |
|---|---|
| **12/10 21h (Brasília) = 13/10 00:00 UTC** | **congelamento**: fotos capturadas antes disso são de treino; depois, teste prospectivo |
| 13/10 em diante | splits definitivos e treino (Guilherme, com o Rodrigo aprovando) |
| 13/10 → 18/10 | **teste C prospectivo**: chuva que ninguém viu quando o modelo foi desenhado (a prova mais forte para a banca) |
| 18/10 | última colheita; avaliação sem retreinar |
| 20/10 | prazo final |

**O que isso quer dizer para câmeras novas, achadas agora:**
- fotos de **depois** do congelamento (ao vivo e DVR de 13/10 em diante) entram no **teste C** — útil e certo;
- fotos de **antes** (o DVR ainda alcança ~5 dias para trás) só entram no **treino** se o Rodrigo aceitar ao
  montar os splits. Colete mesmo assim e avise no RESUMO de entrega quais câmeras/períodos são de antes de 13/10.

## 6. Onde a equipe está (13/10, noite)

| | seco | garoa | moderada | forte |
|---|---|---|---|---|
| acervo do Rodrigo (regra estrita) | 1.122 | 5.884 | 64 | 0 |
| coleta do Guilherme no feriado (prévia) | 4.746 | 3.003 | 765 (25 eventos) | 143 (6 eventos) |
| irCNN (dataset público) | 74 | 555 | 5.311 | 10.469 |

Grande parte da moderada/forte do Guilherme está **travada por posição não verificada**: posição certa vale ouro.

## 7. Lições do fim de semana (para não repetir)

1. **YouTube bloqueia rajada.** 5 downloads de DVR em paralelo → "confirme que não é um robô" → o coletor ao vivo
   do mesmo PC caiu por 2 h. Por isso: um trecho por vez, blocos de 30 min, pausa de 30 min, parar no 1º aviso.
   Contornar (cookies da conta Google, VPN, outra rede) **não**: é burlar a proteção e arrisca a conta.
2. **Relógio do PC.** Windows sem sincronização = 7 min de erro em todas as fotos ao vivo.
3. **Windows.** O `coletor.py` original falha ("Permission denied"); o `ao_vivo.py` do kit corrige.
4. **Estação com defeito existe.** A Jardim João XXIII (Taboão) marcava 0,2 mm a cada 6 h, todo dia — virou 630
   "garoas" falsas. Desconfie de padrão regular demais e anote em `estacoes_com_defeito.txt`.
5. **Câmeras congelam e lives caem/trocam de link.** O coletor descarta foto idêntica ("repetido") e tenta de novo;
   quando o erro for "video not available", procure a live nova no canal.
6. **Live que reinicia todo dia não tem passado** (Porto Alegre, Petrópolis): só o ao vivo serve.
7. **Câmera com "Preset" na tela gira** (Pitangueiras): descartar.
8. **Leia a descrição inteira**: endereço, link de mapa e proibição de uso aparecem lá.

## 8. Divisão de trabalho e cuidados

- **Guilherme**: continua as 16 câmeras de `cameras_ja_capturadas.csv` (ao vivo + DVR + PED delas) e o treino.
- **Paulo / Moreno**: câmeras **novas**, cada um na sua pasta (`--nome`), com a **sua** conta do PED. Avisem no
  grupo cada câmera que pegarem, para não duplicar.
- Nunca commitar: `ml/.env`, `ml/configs/coleta_fixa_tokens.json`, imagens, `ml/data/`, `ml/runs/`.
- Mudanças de código/config vão por branch + PR; o Rodrigo faz o merge.
- Regras que não se mexem: as 4 classes, os limiares, os folds, a câmera de teste (BC) e o congelamento.
