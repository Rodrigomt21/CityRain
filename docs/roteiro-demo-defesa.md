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
