#!/usr/bin/env bash
# Implanta o código de ml/scripts/captura/ na Jetson e confere a saúde do pipeline.
#
#   ml/scripts/captura/implantar_jetson.sh verificar   # só diagnóstico, não muda nada
#   ml/scripts/captura/implantar_jetson.sh implantar   # backup + sync + units + restart + diagnóstico
#
# Pressupõe `ssh jetson` configurado (ver memória/README: se der "Permission denied",
# rodar `ssh-add --apple-load-keychain` no Mac). NÃO sobrescreve cityrain_config.json
# (carrega a api_key do device) nem pesos de modelo (.onnx/.pth) — só avisa se faltar.
set -euo pipefail

HOST="${JETSON_HOST:-jetson}"
REMOTO=/home/jetson/scripts
AQUI="$(cd "$(dirname "$0")" && pwd)"
SERVICOS=(citycam gps uploader sessao botao-desliga wifi-watchdog)

ssh_j() { ssh -o ConnectTimeout=8 -o BatchMode=yes "$HOST" "$@"; }

verificar() {
  echo "== conexão"
  ssh_j 'echo "ok: $(hostname) $(uname -m), uptime $(uptime -p)"'
  echo "== relógio (a Nano não tem RTC: sem NTP o timestamp sai errado)"
  ssh_j 'date -u +"%Y-%m-%dT%H:%M:%SZ"; timedatectl show -p NTPSynchronized --value 2>/dev/null | sed "s/^/NTP sincronizado: /"'
  echo "Mac: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "== câmera"
  ssh_j 'ls /dev/video* 2>/dev/null || echo "NENHUMA câmera em /dev/video*"'
  echo "== disco"
  ssh_j 'df -h /home | tail -1; echo "frames na fila: $(ls /home/jetson/frames/*.jpg 2>/dev/null | wc -l)"'
  echo "== modelo do gate e config"
  ssh_j "python3 - <<'PY'
import json,os
c=json.load(open('$REMOTO/cityrain_config.json'))
m=c.get('modelo_chuva_path','')
print('modelo do gate:', m, '(existe)' if os.path.exists(m) else '(FALTANDO)')
print('backend_url:', c.get('backend_url'))
print('token:', 'definido' if c.get('token') and 'COLE_AQUI' not in str(c.get('token')) else 'FALTANDO (registrar device no backend)')
PY"
  echo "== chaves que o example tem e a config da placa não"
  python3 - "$AQUI/cityrain_config.example.json" <<PY
import json,subprocess,sys
ex=json.load(open(sys.argv[1]))
rem=json.loads(subprocess.run(["ssh","-o","BatchMode=yes","$HOST","cat $REMOTO/cityrain_config.json"],capture_output=True,text=True).stdout)
faltam=sorted(set(ex)-set(rem)); print("faltam:", faltam or "nenhuma")
PY
  echo "== serviços"
  for s in "${SERVICOS[@]}"; do printf "%-15s %s\n" "$s" "$(ssh_j "systemctl is-active $s.service 2>/dev/null || true")"; done
  echo "== GPS (último fix)"
  ssh_j 'cat /run/cityrain/gps.json 2>/dev/null; echo; journalctl -u gps.service -n 3 --no-pager 2>/dev/null | tail -3'
  echo "== uploader (últimas linhas)"
  ssh_j 'journalctl -u uploader.service -n 8 --no-pager 2>/dev/null | tail -8'
}

implantar() {
  ts=$(date +%Y%m%d_%H%M%S)
  echo "== backup remoto em /home/jetson/backups/scripts-$ts"
  ssh_j "mkdir -p /home/jetson/backups && cp -a $REMOTO /home/jetson/backups/scripts-$ts"
  echo "== sincronizando código (sem config, sem pesos, sem apagar nada que só existe na placa)"
  rsync -av --exclude 'cityrain_config.json' --exclude '*.onnx' --exclude '*.pth' --exclude '*.whl' \
    --exclude '__pycache__' --exclude '*.md' --exclude 'mock_backend.py' \
    "$AQUI/" "$HOST:$REMOTO/"
  echo "== units do systemd (pede a senha de sudo da Jetson)"
  ssh -t "$HOST" "sudo cp $REMOTO/systemd/*.service /etc/systemd/system/ && sudo systemctl daemon-reload && \
    sudo systemctl enable ${SERVICOS[*]/%/.service} && sudo systemctl restart ${SERVICOS[*]/%/.service}"
  sleep 5
  verificar
}

case "${1:-verificar}" in
  verificar) verificar ;;
  implantar) implantar ;;
  *) echo "uso: $0 verificar|implantar" >&2; exit 2 ;;
esac
