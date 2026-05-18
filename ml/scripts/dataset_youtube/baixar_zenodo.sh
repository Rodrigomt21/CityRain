#!/usr/bin/env bash
# Baixa e extrai o dataset RaindropsOnWindshield (Zenodo 4680442).
# 8190 imagens de para-brisa em movimento (urbano + rodovia), das quais 3390 têm gotas.
# https://github.com/EvoCargo/RaindropsOnWindshield
set -euo pipefail

cd "$(dirname "$0")"
DEST="raindrops_zenodo"
ZIP="RaindropsOnWindshield.zip"
URL="https://zenodo.org/records/4680442/files/RaindropsOnWindshield.zip?download=1"
MD5_ESPERADO="0ea1b373c981f8ed3ecd311d6596ec0f"

mkdir -p "$DEST"
cd "$DEST"

if [[ -d "RaindropsOnWindshield" && -n "$(ls -A RaindropsOnWindshield 2>/dev/null)" ]]; then
  echo "↷ Dataset já extraído em $DEST/RaindropsOnWindshield — nada a fazer"
  exit 0
fi

need_download=true
if [[ -s "$ZIP" ]]; then
  zip_size=$(stat -f%z "$ZIP" 2>/dev/null || stat -c%s "$ZIP")
  echo "↷ $ZIP já existe ($(du -h "$ZIP" | cut -f1)) — tentando retomar/verificar"
  # 7.4 GB esperado (~7,400,000,000 bytes); continua até estar próximo
  if (( zip_size >= 7400000000 )); then
    need_download=false
  fi
fi

if $need_download; then
  echo "↓ Baixando $ZIP (~7.4 GB) com aria2c (16 conexões)..."
  if command -v aria2c >/dev/null 2>&1; then
    aria2c \
      --continue=true \
      --max-connection-per-server=16 \
      --split=16 \
      --min-split-size=1M \
      --max-tries=5 \
      --retry-wait=5 \
      --file-allocation=none \
      --console-log-level=warn \
      --summary-interval=10 \
      -o "$ZIP" \
      "$URL"
  else
    curl -L -C - --retry 5 --retry-delay 5 -o "$ZIP" "$URL"
  fi
fi

echo "✓ Verificando MD5..."
MD5_REAL=$(md5 -q "$ZIP")
if [[ "$MD5_REAL" != "$MD5_ESPERADO" ]]; then
  echo "✗ MD5 não bate: esperado=$MD5_ESPERADO, real=$MD5_REAL"
  exit 1
fi
echo "  MD5 OK"

echo "↻ Extraindo..."
unzip -q "$ZIP"
echo "✓ Pronto. Conteúdo em $DEST/"
ls -lh
