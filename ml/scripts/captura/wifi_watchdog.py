import subprocess
import time

# Semana 1: dongle RTL8188EU (driver r8188eu, staging) + hotspot de iPhone
# apresentaram desconexao real de ~36 min (ssid-not-found) durante teste em
# 2026-07-29 - a rede autoconnect do NetworkManager fica tentando sozinha,
# mas nao se recupera rapido. Este watchdog nao inventa conectividade onde
# nao ha sinal: so forca um reset do estado do driver (down/up na interface)
# quando fica tempo demais sem conexao, o que ajuda a destravar o driver
# quando o sinal ja esta disponivel de novo mas o wlan0 ficou preso.

INTERVALO_CHECAGEM_S = 30
LIMIAR_RECONEXAO_S = 300  # 5 min sem conexao antes de intervir


def estado_wlan0():
    """Estado atual do dispositivo wlan0 ('connected', 'disconnected' etc.),
    ou None se o dispositivo nem aparecer (dongle desconectado/travado)."""
    try:
        saida = subprocess.run(
            ["nmcli", "-t", "-f", "DEVICE,STATE", "device", "status"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, timeout=10, check=True,
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None
    for linha in saida.strip().splitlines():
        partes = linha.split(":")
        if len(partes) >= 2 and partes[0] == "wlan0":
            return partes[1]
    return None


def reinicia_interface_wifi():
    print(f"[wifi-watchdog] wlan0 sem conexao ha mais de {LIMIAR_RECONEXAO_S}s "
          f"- reiniciando a interface (down/up) para destravar o driver")
    subprocess.run(["ip", "link", "set", "wlan0", "down"], timeout=10)
    time.sleep(2)
    subprocess.run(["ip", "link", "set", "wlan0", "up"], timeout=10)


def main():
    desconectado_desde = None

    while True:
        estado = estado_wlan0()

        if estado == "connected":
            if desconectado_desde is not None:
                print("[wifi-watchdog] wlan0 reconectado")
            desconectado_desde = None
        else:
            agora = time.monotonic()
            if desconectado_desde is None:
                desconectado_desde = agora
                print(f"[wifi-watchdog] wlan0 nao conectado (estado={estado!r}), monitorando")
            elif agora - desconectado_desde >= LIMIAR_RECONEXAO_S:
                reinicia_interface_wifi()
                # reinicia a contagem: da tempo do NetworkManager tentar
                # reassociar sozinho antes do watchdog intervir de novo
                desconectado_desde = time.monotonic()

        time.sleep(INTERVALO_CHECAGEM_S)


if __name__ == "__main__":
    main()
