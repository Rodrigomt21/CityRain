import cv2
import json
import os
import shutil
import socket
import time
from datetime import datetime, timezone

# Pasta absoluta onde os frames serão salvos
FRAMES_DIR = "/home/jetson/frames"
os.makedirs(FRAMES_DIR, exist_ok=True)

CONFIG_PATH = "/home/jetson/scripts/cityrain_config.json"
GPS_ESTADO_PATH = "/run/cityrain/gps.json"


def carrega_device_id():
    """Lê device_id do config compartilhado com o uploader; se o arquivo ainda
    não existir (ou estiver sem o campo), usa o hostname como fallback."""
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f).get("device_id") or socket.gethostname()
    except (FileNotFoundError, json.JSONDecodeError):
        return socket.gethostname()


def le_gps():
    """Lê o último fix conhecido do gps.service. Se o arquivo não existir ou
    estiver corrompido (serviço parado, escrita em andamento), retorna None —
    a captura de frame nunca pode falhar por causa do GPS."""
    try:
        with open(GPS_ESTADO_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def salva_metadado(caminho_json, metadado):
    """Mesmo padrão atômico do gps.py: tmp + os.replace, para quem for ler
    (o uploader) nunca ver um JSON parcialmente escrito."""
    tmp_path = caminho_json + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(metadado, f)
    os.replace(tmp_path, caminho_json)


DEVICE_ID = carrega_device_id()

# Guarda de espaço em disco: NÃO apaga nada (não há pipeline de upload ainda,
# então apagar frame seria perder dado de campo). Só pausa a gravação de
# frames novos se o disco ficar perigosamente cheio, evitando escrita
# corrompida / filesystem cheio. Volta a gravar sozinho assim que houver
# espaço de novo (ex.: alguém copiar os frames pra outro lugar).
ESPACO_MINIMO_MB = 500
AVISO_INTERVALO_S = 60  # não loga a cada frame enquanto pausado, só 1x/min

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("Erro: não foi possível abrir a câmera")
    exit(1)

# Opcional: define resolução (descomente se quiser forçar)
# cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

ultimo_aviso_espaco = 0.0

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Falha na leitura do frame, tentando novamente em 5s")
            time.sleep(5)
            continue

        espaco_livre_mb = shutil.disk_usage(FRAMES_DIR).free / (1024 * 1024)
        if espaco_livre_mb < ESPACO_MINIMO_MB:
            agora = time.monotonic()
            if agora - ultimo_aviso_espaco > AVISO_INTERVALO_S:
                print(f"Espaço em disco abaixo de {ESPACO_MINIMO_MB}MB "
                      f"({espaco_livre_mb:.0f}MB livres) — pausando gravação de frames novos")
                ultimo_aviso_espaco = agora
            time.sleep(1)
            continue

        # Timestamp com milissegundos: AAAAMMDD_HHMMSS_mmm
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        nome_arquivo = f"frame_{timestamp}.jpg"
        caminho = os.path.join(FRAMES_DIR, nome_arquivo)
        sucesso = cv2.imwrite(caminho, frame)

        if not sucesso:
            print(f"Falha ao salvar {caminho}")
        else:
            # O .json só é escrito depois do .jpg: sua presença marca pro
            # uploader que o par está completo e pronto pra fila.
            metadado = {
                "schema": 1,
                "device_id": DEVICE_ID,
                "capturado_em_utc": datetime.now(timezone.utc).isoformat(),
                "arquivo": nome_arquivo,
                "gps": le_gps(),
            }
            caminho_json = os.path.join(FRAMES_DIR, f"frame_{timestamp}.json")
            salva_metadado(caminho_json, metadado)

        time.sleep(1)
finally:
    cap.release()
