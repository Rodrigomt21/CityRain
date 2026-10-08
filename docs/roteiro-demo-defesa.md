# Roteiro da demonstração ao vivo (defesa)

> Objetivo: mostrar o sistema inteiro funcionando na frente da banca, **sem depender de chover**,
> com o pipeline de produção de verdade. Duração: ~3 min de replay.

## O que acontece

A Jetson reproduz a sessão real de **23/09/2026** (chuva, 6–19 mm/h nas estações próximas) como se
o carro estivesse rodando agora: `demo_replay.py` deposita 1 frame a cada 2 s na fila da câmera,
com horário atual e GPS original. A partir daí é tudo produção: `uploader.service` → gate →
`POST /api/v1/ingest` (Railway) → modelo de intensidade no backend → PostgreSQL → dashboard.
As capturas de demonstração ficam marcadas em `metadata.demo` no banco (nunca se misturam
com as reais).

## Antes (no dia, 10 min)

1. Jetson ligada na rede (cabo ou Wi-Fi), `ssh jetson` funcionando
   (se `Permission denied`: `ssh-add --apple-load-keychain`).
2. Conferir: `ml/scripts/captura/implantar_jetson.sh verificar` (uploader `active`, backend de
   produção, token definido).
3. Abrir o dashboard com atualização rápida:
   ```
   cd frontend && VITE_POLL_MS=5000 npm run dev
   ```
   Abas: `http://localhost:5173/dashboard` (ao vivo) e `http://localhost:5173/historico` (mapa H3).

## Durante

1. Mostrar o dashboard parado ("SIMULAÇÃO · API sem capturas" ou dispositivo offline).
2. Disparar o replay:
   ```
   ssh jetson 'python3 /home/jetson/scripts/demo_replay.py --origem /home/jetson/demo/sessao_2309 --intervalo 2 --decisao estacao'
   ```
   `--decisao estacao` usa o rótulo de estação para a decisão chuva/seco; `--decisao gate` mostra o
   gate real da placa (que hoje deixa passar só parte da chuva — ver resultados).
3. Em ~10 s o dashboard vira **AO VIVO**, o ponto da Jetson aparece no mapa e a classe muda
   conforme o modelo classifica cada frame. Na aba Histórico, o trajeto aparece em células H3.
4. Ponto a narrar: "cada imagem atravessou a API pública, foi classificada pelo modelo exportado
   em ONNX e gravada no banco — isto é produção, não um vídeo".

## Depois

As capturas de demonstração têm `metadata.demo` preenchido. Para relatórios, filtrar fora
(`metadata->'demo' IS NULL`).

## Câmera fixa (~3 min)

> Objetivo: mostrar o pipeline de produção com câmeras fixas (lives públicas, CCTV, webcam),
> com a intensidade classificada pelo modelo de câmera fixa.

### Antes (no dia, 5 min)

1. Confirmar o deploy: `https://<backend>/openapi.json` deve listar `/api/v1/cameras/`. Não use `/health`
   para datar o deploy (responde igual em qualquer versão). O painel do Railway só entra se o deploy
   estiver travado.
2. Cada câmera precisa estar registrada como dispositivo `fixa-<id>` (tipo `fixa`) e ter o token em
   `ml/configs/coleta_fixa_tokens.json` ou em `CITYRAIN_TOKEN_<ID>`.
3. Iniciar o coletor no Mac:
   ```
   caffeinate -i ml/.venv/bin/python ml/scripts/coleta_fixa/coletor.py ml/configs/coleta_fixa.yaml --enviar --intervalo-s 60
   ```
4. Depois do primeiro envio do coletor, conferir que o modelo de câmera fixa está carregado:
   `GET /api/v1/cameras/` deve trazer, para cada câmera, `ultima_captura.modelo` e `weather_label`
   não nulos. Se vierem nulos, o `intensidade_fixa.onnx` não está no backend: não siga para a demo.
5. Abrir o dashboard com polling rápido (`cd frontend && VITE_POLL_MS=5000 npm run dev`) ou usar
   https://cityrain.vercel.app, e ir para `/cameras`.

### Ao vivo

1. Em `/cameras` (grade) cada card mostra a `descricao` da câmera e a última classe. Clique no card
   para abrir o detalhe: o id na URL (`/cameras/<id>`) é o id numérico do dispositivo, diferente do id
   da fonte usado no `--camera` do replay (ex.: `bc_atlantica`).
2. O detalhe mostra o último frame capturado, a série temporal (3, 6 e 24 h) e o link "abrir
   transmissão" (leva à live original; a página não exibe vídeo ao vivo).
3. Sem chuva, o modelo deve mostrar `seco`: isso também demonstra que ele está inferindo.

### Replay de evento

1. **Antes da defesa**, escolha o evento filtrando `ml/data/splits/fixa_v1.csv` (colunas `evento_id`,
   `classe`, `ts_utc`, `periodo`, `camera`). O resumo do `montar_splits_fixa.py` só traz contagens.
   Exemplo (câmera de teste, classe forte):
   ```
   ml/.venv/bin/python - <<'PY'
   import csv
   for r in csv.DictReader(open("ml/data/splits/fixa_v1.csv")):
       if r["camera"] == "bc_atlantica" and r["classe"] in ("moderada", "forte"):
           print(r["evento_id"], r["classe"], r["periodo"], r["ts_utc"])
   PY
   ```
   Use o menor e o maior `ts_utc` do evento como `--de`/`--ate`.
2. Use SEMPRE a câmera de teste do `ml/configs/splits_fixa_v1.yaml` (`camera_teste: bc_atlantica`):
   só assim a frase "câmera que o modelo nunca viu" é verdadeira.
3. O período do evento (`dia`/`noite`) precisa ser o de agora (dia = 06:00 a 18:30 em UTC-3): o backend
   escolhe a referência seca pelo horário do envio. O replay aborta se forem diferentes
   (`--forcar-periodo` ignora, com aviso, e a classificação sai com a referência errada). Para uma
   defesa de dia, escolha evento de `periodo` = `dia`.
4. Disparar:
   ```
   ml/.venv/bin/python ml/scripts/coleta_fixa/replay_evento.py --camera bc_atlantica --de <ISO> --ate <ISO> --intervalo 2
   ```
   Datas sem fuso são lidas como -03:00 (o script avisa). No fim ele imprime o resumo
   (ok / duplicados / erros / sem rede); 0 frames ou HTTP 401/403/422 encerram com erro.
5. O coletor envia um ponto real a cada 60 s dessa mesma fonte. Ou pause a fonte `bc_atlantica` no
   coletor durante o replay, ou avise a banca de que pontos reais se intercalam com os do replay.
6. No detalhe da câmera a classe deve subir conforme os frames são processados. As capturas do replay
   têm `metadata.demo` e não aparecem no Histórico; ensaiar várias vezes é seguro (cada envio muda só
   um comentário JPEG, então o hash difere).

### Frase para a banca

"Cada frame atravessou a API pública e foi classificado pelo modelo de câmera fixa, treinado só com
chuva real medida por pluviômetro. O teste foi por evento e numa câmera que o modelo nunca viu."

### Plano B (sem rede: tudo local, três comandos)

1. Backend local (a partir de `backend/`, com Postgres local rodando e o banco criado):
   ```
   cd backend
   export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/cityrain ADMIN_KEY=demo
   .venv/bin/alembic upgrade head          # só na primeira vez
   .venv/bin/python -m uvicorn app.main:app --port 8000
   ```
2. Frontend apontando para ele:
   ```
   cd frontend && VITE_API_URL=http://localhost:8000 VITE_POLL_MS=5000 npm run dev
   ```
3. Replay no backend local:
   ```
   ml/.venv/bin/python ml/scripts/coleta_fixa/replay_evento.py --camera bc_atlantica --de <ISO> --ate <ISO> \
       --intervalo 2 --api http://localhost:8000/api/v1/ingest
   ```

Checklist (fazer antes, com rede):

- [ ] Registrar o dispositivo `fixa-<id>` no backend local e colocar o token devolvido em
      `ml/configs/coleta_fixa_tokens.json` (o token de produção não vale no banco local):
      ```
      curl -X POST http://localhost:8000/api/v1/devices/ -H "Authorization: Bearer demo" \
        -H "Content-Type: application/json" \
        -d '{"name":"fixa-bc_atlantica","tipo":"fixa","latitude":-26.99,"longitude":-48.63,"stream_url":"https://...","descricao":"BC Atlântica"}'
      ```
- [ ] `backend/app/inference/modelos/intensidade_fixa.onnx` presente (ou `INFERENCE_MODEL_FIXA_PATH`).
- [ ] `backend/app/inference/referencias/fixa-<id>/{dia,noite}.jpg` presentes
      (ou `REFERENCIAS_DIR`).
- [ ] Ensaiar uma vez inteira com o Wi-Fi desligado.
