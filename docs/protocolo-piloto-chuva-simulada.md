# Piloto: chuva simulada no para-brisa com intensidade medida

> 05/10/2026. Duração: **~1 h** de campo. Objetivo: decidir, com número, se água
> aplicada no para-brisa com taxa medida produz imagens parecidas com chuva real —
> e, se sim, virar o **teste calibrado do domínio carro** para moderada/forte, que
> hoje não existe (sessões do carro: 454 de 492 frames entre 1 e 2,5 mm/h).

## Por que (e o limite)

O que só o carro tem é **água no vidro + limpador**. As câmeras fixas e o irCNN cobrem a
névoa/riscos no ar, não o vidro. Simulador de chuva é método usado em pesquisa de sensores
automotivos; aqui ele mede **só a componente do vidro** — sem céu escuro, pista molhada nem
névoa. Isso vai escrito como limitação, e o conjunto é usado como **teste**, não treino.

## Material

- O carro, a **câmera C270 montada como na coleta** (mesma posição/ângulo) e a Jetson capturando (`citycam.service`, 1 fps). Sem Jetson: celular fixo atrás do vidro, mesmo enquadramento.
- Mangueira com **chuveirinho/regulador de jato** (ou regador de crivo fino).
- **Pluviômetro caseiro:** recipiente de boca reta e larga (pote/balde), régua para medir o diâmetro, copo medidor (ml).
- Cronômetro (celular) e uma folha para anotar.

## Medir o mm/h (antes de cada nível, 1 min)

1. Pote ao lado do para-brisa, **na mesma altura**, sob o mesmo jato, por **t = 1 min**.
2. Medir o volume coletado **V (ml)** e a área da boca **A (cm²)** = π·(diâmetro/2)².
3. **mm/h = (V / A) × 10 × (60 / t)**. Ex.: V = 20 ml, boca de 15 cm (A = 177 cm²), t = 1 min → 6,8 mm/h.

Repetir a medida no fim do nível; usar a média. Anotar a hora de início/fim (relógio da Jetson).

## Níveis (5 min cada, nesta ordem)

| Nível | Alvo | Limpador |
|---|---|---|
| 0. seco | 0 mm/h | parado |
| 1. leve | ~1–2 mm/h | parado |
| 2. moderado | ~4–8 mm/h | parado, depois 1 min intermitente |
| 3. forte | ~15–30 mm/h | parado 2 min, depois ligado 3 min |

Entre níveis, esperar o vidro escorrer 1 min. Se der tempo, repetir o nível 3 com o jato
**mais espalhado** (gotas menores) — é o que mais difere de chuva natural.

## Critério de decisão (fixado ANTES de ver as imagens)

Eu meço com a régua do projeto (`ml/scripts/sintetico/medir_regua.py`: contraste RMS,
nitidez, densidade e tamanho de gotas) e comparo com chuva real do mesmo domínio
(23/09 e vídeos YouTube forte):

1. **Aparência:** contraste e nitidez do nível 3 dentro da faixa do YouTube forte real
   (contraste 0,22–0,28; nitidez 0,5–14) e tamanho mediano de gota no máximo 2× o de 23/09.
2. **Ordenação:** o score do modelo de produção cresce com o mm/h medido
   (Spearman ≥ 0,7 entre níveis).

- Passou em 1 e 2 → vira `test_simulado_parabrisa` (teste calibrado do carro) e, se o
  número de frames permitir, uma rodada a mais com 2–3 repetições por nível.
- Passou em 1, falhou em 2 → teste válido, e o resultado mostra a fraqueza do modelo no
  vidro (entra no texto como resultado).
- Falhou em 1 → descarta; documentar como tentativa (aparência artificial demais).

## O que me mandar

A pasta de frames da Jetson do horário do piloto (ou os vídeos do celular) e a folha com
**hora início/fim + V, A, t** de cada nível. O resto (régua, rótulos, avaliação) é comigo.
