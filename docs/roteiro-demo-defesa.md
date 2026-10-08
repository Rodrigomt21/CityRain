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

> Objetivo: demonstrar o sistema em funcionamento com um colector de câmera fixa (CCTV, webcam ou câmera IP),
> mostrando que o pipeline funciona para qualquer tipo de câmera, com rótulos gerados em tempo real.

### Antes (no dia, 5 min)

1. Confirmar que o modelo de câmera fixa está em produção no backend: verificar `/openapi.json` e procurar
   por `/api/v1/cameras/` (não verificar `/health`; a verificação de deploy deve ser feita pelo painel do Railway).
2. Registrar a câmera fixa no backend como dispositivo `fixa-<id>` com tipo `fixa`. O token de ingestão
   deve estar em `ml/configs/coleta_fixa_tokens.json` ou como variável de ambiente `CITYRAIN_TOKEN_<id>`.
3. Iniciar o coletor de câmera fixa no Mac com:
   ```
   caffeinate -i ml/.venv/bin/python ml/scripts/coleta_fixa/coletor.py ml/configs/coleta_fixa.yaml --enviar --intervalo-s 60
   ```
4. Abrir o dashboard com polling rápido:
   ```
   cd frontend && VITE_POLL_MS=5000 npm run dev
   ```
   Ou usar a versão em produção: https://cityrain.vercel.app.
5. Navegar até a página `/cameras` (grade com todas as câmeras registradas).

### Ao vivo

1. Mostrar a grade de câmeras (`/cameras`): todos os `fixa-<id>` devem estar listados.
2. Clicar em uma câmera para abrir a página de detalhe (`/cameras/<id>`), que mostra:
   - Transmissão original da câmera em tempo real.
   - Série temporal das últimas 3, 6 e 24 horas com a classificação de intensidade (`seco`, `garoa`,
     `moderada`, `forte`).
3. Se não houver chuva no momento, o sistema deve mostrar a classe `seco` correta, demonstrando que
   o modelo está inferindo mesmo sem precipitação.

### Replay de evento

1. **Antes da defesa**, consultar o resumo do script de montagem de splits:
   ```
   ml/scripts/dataset/montar_splits_fixa.py
   ```
   e escolher um evento com classe **moderada** ou **forte** (consultar as listas `por_particao_classe` e
   `por_camera` no resumo).
2. Preparar os timestamps ISO com fuso horário (ex: `2026-10-01T18:00:00-03:00`) do evento selecionado.
3. Durante a defesa, disparar o replay com:
   ```
   ml/.venv/bin/python ml/scripts/coleta_fixa/replay_evento.py --camera <id> --de <ISO com fuso> --ate <ISO com fuso> --intervalo 2
   ```
4. Acompanhar a série temporal no detalhe da câmera (`/cameras/<id>`): a classe de intensidade deve
   subir conforme os frames do replay são processados e classificados pelo modelo.
5. As capturas do replay ficam marcadas com `metadata.demo` no banco de dados e são ocultadas na página
   Histórico; é seguro ensaiar várias vezes (cada envio modifica apenas o comentário JPEG).

### Frase para a banca

"Cada frame atravessou a API pública e foi classificado pelo modelo de câmera fixa, treinado só com
chuva real medida por pluviômetro. O teste foi por evento e numa câmera que o modelo nunca viu."

### Plano B (se a rede cair)

1. Encerrar o coletor (`Ctrl+C`).
2. Seguir as instruções em `docs/COMO-CONTINUAR.md` para iniciar o backend localmente.
3. Reenviar o replay com o argumento:
   ```
   --api http://localhost:8000/api/v1/ingest
   ```
