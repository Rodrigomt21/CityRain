import cv2
import json
import os
import shutil
import socket
import time
from datetime import datetime, timezone

# Pasta absoluta onde os frames serão salvos
FRAMES_DIR = "/home/jetson/frames"

CONFIG_PATH = "/home/jetson/scripts/cityrain_config.json"
GPS_ESTADO_PATH = "/run/cityrain/gps.json"

# Guarda de espaço em disco: NÃO apaga nada (não há pipeline de upload ainda,
# então apagar frame seria perder dado de campo). Só pausa a gravação de
# frames novos se o disco ficar perigosamente cheio, evitando escrita
# corrompida / filesystem cheio. Volta a gravar sozinho assim que houver
# espaço de novo (ex.: alguém copiar os frames pra outro lugar).
ESPACO_MINIMO_MB = 500
AVISO_INTERVALO_S = 60  # não loga a cada frame enquanto pausado, só 1x/min


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


def _grava_duravel(caminho_final, escreve_em):
    """Escreve via .tmp + fsync + rename: o nome final só passa a existir
    quando o conteúdo já está fisicamente no disco.

    Isso existe porque a alimentação em campo é instável (ver J5 da spec): sem
    o fsync, um corte de energia deixa o arquivo com nome final e 0 byte, e o
    uploader trata esse par como válido. Mediu-se 21% de perda assim numa
    única sessão (63 de 305 frames, 23/09).
    """
    tmp = caminho_final + ".tmp"
    escreve_em(tmp)
    fd = os.open(tmp, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, caminho_final)


def _fsync_diretorio(caminho):
    """Torna os renames acima duráveis — o rename é metadado de diretório e
    também pode ser perdido num corte de energia."""
    fd = os.open(caminho, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def salva_frame_duravel(caminho_jpg, frame):
    """Grava o frame capturado como jpg, só tornando `caminho_jpg` visível
    depois que o conteúdo está fisicamente no disco (ver `_grava_duravel`).

    Usa `cv2.imencode` (não `cv2.imwrite` direto no `.tmp`): o `imwrite`
    escolhe o codificador pela *extensão do nome do arquivo*, e o nosso `.tmp`
    termina em `.tmp`, não em `.jpg` — `cv2.imwrite(caminho + ".tmp", frame)`
    levanta `cv2.error: could not find a writer for the specified extension`
    em toda chamada (confirmado com o OpenCV 3.2.0 real da Jetson). Codificar
    para bytes primeiro e escrever esses bytes com `open(tmp, "wb")` deixa a
    escrita do `.tmp` igual à do json (bytes crus, sem cv2 olhar pro nome do
    arquivo) — não dá pra "resolver" trocando pra `caminho + ".tmp.jpg"`,
    porque o mesmo padrão aplicado ao json viraria `.tmp.json`, que passaria
    no filtro de `pares_pendentes()` do uploader como metadado pronto.

    Levanta `cv2.error` (falha de codificação) ou `IOError` (`imencode`
    reportou sucesso mas devolveu False) — quem chama decide o que fazer
    (hoje: logar e pular o frame, sem derrubar o laço).
    """
    def escreve(tmp):
        ok, buffer = cv2.imencode(".jpg", frame)
        if not ok:
            raise IOError("cv2.imencode falhou para {}".format(caminho_jpg))
        with open(tmp, "wb") as f:
            f.write(buffer.tobytes())

    _grava_duravel(caminho_jpg, escreve)


def salva_metadado_duravel(caminho_json, metadado):
    """Grava o metadado do frame como json, só tornando `caminho_json`
    visível depois que o conteúdo está fisicamente no disco (ver
    `_grava_duravel`). Mesmo padrão atômico do `gps.py`, com o `fsync`
    adicional que faltava (ver J1 da spec)."""
    def escreve(tmp):
        with open(tmp, "w") as f:
            json.dump(metadado, f)

    _grava_duravel(caminho_json, escreve)


def main():
    """Laço principal de captura: abre a câmera e grava um par jpg+json
    durável por segundo, até ser interrompido.

    Extraído do nível de módulo (e protegido por `if __name__ == "__main__"`)
    para que este arquivo possa ser importado em teste sem abrir câmera nem
    entrar num laço infinito — o comportamento de execução direta
    (`python3 captura.py`, como o `citycam.service` faz) não muda.
    """
    os.makedirs(FRAMES_DIR, exist_ok=True)
    device_id = carrega_device_id()

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

            try:
                salva_frame_duravel(caminho, frame)
            # cv2.error não herda de IOError (confirmado na Jetson: MRO
            # termina em Exception/BaseException/object) — sem capturar os
            # dois, uma falha de codificação escapa do laço, mata o processo
            # e o citycam.service (Restart=always) entra em crash-loop sem
            # capturar frame nenhum, muito pior que o problema que o J1 quer
            # resolver.
            except (IOError, cv2.error) as e:
                print(f"Falha ao salvar {caminho}: {e}")
            else:
                # O .json só passa a existir (rename durável) depois do
                # .jpg: sua presença marca pro uploader que o par está
                # completo e pronto pra fila.
                metadado = {
                    "schema": 2,  # 2 = gps traz hora_rmc_utc (A1) e ultimo_fix_em (A2)
                    "device_id": device_id,
                    "capturado_em_utc": datetime.now(timezone.utc).isoformat(),
                    "arquivo": nome_arquivo,
                    "gps": le_gps(),
                }
                caminho_json = os.path.join(FRAMES_DIR, f"frame_{timestamp}.json")
                salva_metadado_duravel(caminho_json, metadado)
                # Sem isso, os dois renames acima (jpg e json) podem não ter
                # durado: rename é metadado de diretório, não conteúdo de
                # arquivo — um corte de energia pode perder só o metadado.
                _fsync_diretorio(FRAMES_DIR)

            time.sleep(1)
    finally:
        cap.release()


if __name__ == "__main__":
    main()
