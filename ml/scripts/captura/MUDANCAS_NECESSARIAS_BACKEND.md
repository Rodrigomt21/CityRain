# Mudanças necessárias no backend — CityRain

Contexto: comparei o `openapi.json` publicado em `https://api-production-046f.up.railway.app/openapi.json`
(conferido ao vivo em 2026-09-15) com o fluxo que a gente pretende rodar na Jetson (gate binário
chuva/não-chuva on-device + upload condicional). Achei 3 pontos que travam a integração — pedindo
confirmação/ajuste antes de apontarmos o `uploader.py` pro backend real.

## 1. Falta endpoint para o caso "sem chuva" (sem foto)

Hoje o único jeito de registrar qualquer captura é `POST /api/v1/ingest`, e nesse endpoint o campo
`image` é **obrigatório** no schema (`Body_ingest_capture_api_v1_ingest_post.required = ["image", "metadata"]`).

A ideia do lado da Jetson é: quando o gate binário classificar o frame como "sem chuva", **não**
subir a foto (economiza banda/dado, já que a foto sem chuva não tem valor pro dataset de intensidade)
e só avisar o backend de alguma forma pra ele contar isso como `"seco"`.

**Não existe hoje um endpoint pra esse caso** (mensagem de status sem imagem). Precisa de uma dessas
duas soluções:
- (a) Um endpoint novo e leve, tipo `POST /api/v1/status` ou `POST /api/v1/captures/no-rain`, que
  aceite só `device_id` + `captured_at` + `latitude`/`longitude`, sem exigir arquivo de imagem; ou
- (b) Tornar `image` opcional em `POST /api/v1/ingest` quando `weather_label == "seco"`.

Qual das duas o Guilherme prefere implementar?

## 2. Quem gera garoa/moderado/forte?

O filtro de `GET /api/v1/captures` e a agregação de `GET /api/v1/stats/geo` usam o enum:

```json
"weather_label": { "enum": ["seco", "garoa", "moderado", "forte"] }
```

Só que o modelo que roda na Jetson (`bestModel.pth`, MobileNetV2) é um **gate binário**: só
diferencia `com_gota` (chuva) de `sem_gota` (sem chuva) — não tem como ele sozinho dizer se é
garoa, moderado ou forte.

Plano do nosso lado: a Jetson só decide **se envia ou não** a foto (chuva → envia, sem chuva → vira
o caso do item 1). A classificação fina de intensidade (garoa/moderado/forte) precisaria continuar
sendo feita em algum lugar — seja um segundo modelo (4 classes) rodando no backend sobre a foto
recebida, seja outra estratégia que o Guilherme já tenha em mente.

**Pergunta direta pro Guilherme**: o backend vai rodar esse classificador de 4 classes sobre a
imagem recebida (arquitetura original discutida em 07/2026), ou espera que `weather_label` já
chegue com uma dessas 3 classes de chuva prontas desde a Jetson? Se for a segunda opção, a Jetson
vai precisar de um modelo de 4 classes também (não temos isso treinado ainda — só o binário).

Isso muda a descrição atual da API (`info.description`: *"O modelo CNN roda na própria Jetson —
weather_label e confidence chegam já classificados"*), que hoje sugere que a Jetson entrega tudo
pronto — o que não bate com o modelo que temos hoje.

## 3. Formalizar `weather_label`/`confidence` no schema de request

No `POST /api/v1/ingest`, o campo `metadata` é tipado só como `string` livre — os campos internos
esperados (`captured_at`, `latitude`, `longitude`, `source_type`, `weather_label`, `confidence`) só
aparecem descritos em texto na documentação, não como propriedades tipadas/obrigatórias de verdade
no schema. Isso significa que erros de nome de campo ou tipo (ex.: mandar `confidence` como 0–100
em vez de 0–1) só vão aparecer em runtime, não no contrato.

Pedido: formalizar o corpo de `metadata` como um schema de objeto tipado (com os campos acima e
seus tipos/ranges esperados), pra validação acontecer no request em vez de silenciosamente.

## 4. O que precisamos pra fechar o contrato seguro (token/registro do device)

`POST /api/v1/devices/` (e todo o resto da API) exige `HTTPBearer`. Olhando o schema de
`DeviceCreate`, o payload de registro é:

```json
{
  "name": "jetson-nano-01",
  "vehicle_plate": null,
  "hw_model": "jetson_nano",
  "metadata_": null
}
```

(o exemplo do schema usa `"jetson_xavier"` em `hw_model`, mas o hardware real desta unidade é
Jetson **Nano** — vale registrar certo desde já pra não confundir métricas/telemetria depois).

A resposta (`DeviceCreatedResponse`) traz um `api_key` que **só aparece uma única vez** — não tem
como recuperar depois, só re-registrar. Por isso precisamos que o Guilherme escolha uma das duas
opções:

- **(a) Ele mesmo registra** o device com o payload acima e nos manda o `api_key` retornado — só
  pedimos que seja por um canal que não fique salvo em texto puro pra sempre (não colar em grupo
  aberto/issue pública; se vazar, ele precisa poder revogar/re-registrar o device); ou
- **(b) Ele nos passa um token admin temporário** (com escopo mínimo, só pra chamar
  `POST /api/v1/devices/`) e nós mesmos rodamos o registro daqui, guardando o `api_key` direto no
  `cityrain_config.json` sem ele passar pelo meio de campo nenhum.

Sem uma dessas duas coisas não dá pra testar nada contra o backend de produção — hoje só
conseguimos validar o pipeline contra o `mock_backend.py` local, que não checa autenticação.

## 5. Suavização temporal (série temporal) — um frame isolado pode estar mentindo

O gate da Jetson decide por **frame individual**, sem olhar a vizinhança temporal. Isso cria um
risco real: no meio de uma sequência de chuva de verdade, um único frame pode sair `sem_gota` por
ruído pontual (limpador de para-brisa passando bem na hora, reflexo, gota escorrendo cobrindo a
lente diferente do resto da sequência) — e, como a Jetson **não envia foto quando classifica
"seco"** (ver item 1), esse frame simplesmente some, sem re-checagem e sem qualquer sinal de que
destoa da vizinhança. É perda silenciosa de dado de chuva real, não um erro visível.

Duas perguntas pro Guilherme, porque a resposta muda o que a Jetson precisa mandar:

- Faz sentido o backend rodar uma análise de série temporal em cima do histórico de capturas por
  device (ordenado por `captured_at`) pra suavizar/corrigir classificações isoladas que destoam da
  vizinhança (ex.: janela deslizante, voto de maioria, ou flag de "outlier" pra revisão)? Isso já é
  uma vantagem de fazer no backend: ele tem o histórico completo por device, a Jetson só vê o
  frame atual.
- Se a suavização for só no backend, ela só enxerga o que a Jetson decidiu mandar. Como hoje a
  Jetson **não sobe foto nenhuma no caso "seco"**, um frame isolado mal classificado nunca chega
  no backend pra ser corrigido — o dado já se perdeu antes de qualquer série temporal rodar. Faz
  sentido a Jetson segurar um pequeno buffer local (ex.: só tratar como "seco" de verdade depois de
  N frames seguidos "sem_gota", tipo o debounce que já usamos no botão de shutdown) antes de
  descartar, em vez de decidir por um frame só? Ou o backend prefere receber todo frame (inclusive
  "seco") pra fazer a suavização com o dado bruto completo, abrindo mão da economia de banda que o
  gate foi criado pra dar?

Ainda não implementamos nada disso na Jetson — preferimos alinhar a arquitetura antes de mexer no
`uploader.py` de novo.

---

*Gerado a partir da inspeção do `openapi.json` ao vivo em 2026-09-15. Se algum desses pontos já
tiver mudado do lado dele, vale reconferir o `/openapi.json` antes de assumir que a dúvida ainda é
válida.*
