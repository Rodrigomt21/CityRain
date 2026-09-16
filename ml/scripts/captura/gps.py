#!/usr/bin/env python3
"""
gps.py — Leitor de GPS (u-blox NEO-6M) via UART, para o CityRain.

Lê sentenças NMEA (GGA/RMC) continuamente e mantém em
/run/cityrain/gps.json o último fix conhecido, em formato que qualquer
outro processo (ex.: captura.py) pode ler a qualquer momento sem
precisar falar com a porta serial diretamente.

Rodar como serviço (gps.service) ou manualmente: python3 gps.py
Encerrar (modo manual): Ctrl+C
"""

import json
import os
import time
from datetime import datetime, timezone

import serial
import pynmea2

# ============================================================
# Configurações
# ============================================================
PORTA = "/dev/ttyTHS1"          # UART do header 40-pin (pinos 8/10)
BAUDRATE = 9600                 # Padrão do NEO-6M
ESTADO_PATH = "/run/cityrain/gps.json"
RECONNECT_DELAY_S = 5           # espera entre tentativas de reabrir a porta
SILENCIO_MAX_S = 15             # sem nenhuma sentença válida por tanto tempo = considera fix perdido


def estado_inicial():
    return {
        "fix": False,           # True só quando o GGA reporta qualidade > 0
        "latitude": None,
        "longitude": None,
        "altitude_m": None,
        "satelites": None,
        "hdop": None,           # precisão horizontal (menor = melhor)
        "status_rmc": None,     # 'A' = válido, 'V' = void, segundo o RMC
        "atualizado_em": None,  # timestamp UTC (relógio do sistema) da última leitura processada
    }


def salvar_estado(estado):
    """Escreve o estado em disco de forma atômica (tmp + rename), para que
    quem estiver lendo o arquivo nunca veja um JSON parcialmente escrito."""
    os.makedirs(os.path.dirname(ESTADO_PATH), exist_ok=True)
    tmp_path = ESTADO_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(estado, f)
    os.replace(tmp_path, ESTADO_PATH)


def processa_linha(linha, estado):
    """Atualiza `estado` a partir de uma linha NMEA. Qualquer linha que não
    seja GGA/RMC, ou que esteja corrompida (ruído na UART), é ignorada sem
    lançar exceção — o pipeline nunca deve quebrar por causa do GPS."""
    if not linha.startswith("$"):
        return False

    try:
        msg = pynmea2.parse(linha)
    except pynmea2.ParseError:
        return False

    agora = datetime.now(timezone.utc).isoformat()

    # A partir daqui os campos já passaram na validação de checksum do
    # pynmea2, mas ainda podem vir em formato inesperado (receptor não
    # conforme, ruído que não derrubou o checksum por coincidência, etc.) —
    # uma sentença malformada não pode derrubar o processo inteiro.
    try:
        if isinstance(msg, pynmea2.types.talker.GGA):
            qualidade = int(msg.gps_qual) if msg.gps_qual not in (None, "") else 0
            estado["fix"] = qualidade > 0
            estado["satelites"] = int(msg.num_sats) if msg.num_sats not in (None, "") else 0
            estado["hdop"] = float(msg.horizontal_dil) if msg.horizontal_dil not in (None, "") else None
            if estado["fix"]:
                estado["latitude"] = msg.latitude
                estado["longitude"] = msg.longitude
                estado["altitude_m"] = msg.altitude
            estado["atualizado_em"] = agora
            return True

        if isinstance(msg, pynmea2.types.talker.RMC):
            estado["status_rmc"] = msg.status
            estado["atualizado_em"] = agora
            return True
    except (ValueError, TypeError) as e:
        print(f"[gps] sentença NMEA com campo em formato inesperado, ignorando: {e}")
        return False

    return False


def main():
    estado = estado_inicial()
    salvar_estado(estado)
    ultima_valida = time.monotonic()

    while True:
        try:
            with serial.Serial(PORTA, BAUDRATE, timeout=1) as ser:
                print(f"[gps] porta {PORTA} aberta a {BAUDRATE} baud, aguardando dados...")
                while True:
                    bruto = ser.readline()
                    linha_valida = False
                    if bruto:
                        try:
                            linha = bruto.decode("ascii", errors="replace").strip()
                            linha_valida = processa_linha(linha, estado)
                        except UnicodeDecodeError:
                            pass

                    if linha_valida:
                        ultima_valida = time.monotonic()
                        salvar_estado(estado)
                    elif estado["fix"] and (time.monotonic() - ultima_valida) > SILENCIO_MAX_S:
                        # Nada de válido chega há tempo demais (antena arrancada, módulo
                        # sem energia, etc.) — o receptor simplesmente parou de falar, o
                        # que não é capturado pelo "gps_qual" de nenhuma sentença porque
                        # não há mais sentença nenhuma chegando. Degrada o fix sozinho,
                        # em vez de deixar a última posição congelada parecendo válida.
                        print(f"[gps] sem sentenças válidas há mais de {SILENCIO_MAX_S}s — "
                              f"marcando fix como perdido")
                        estado["fix"] = False
                        salvar_estado(estado)
        except serial.SerialException as e:
            print(f"[gps] porta indisponível ({e}); tentando de novo em {RECONNECT_DELAY_S}s")
            estado["fix"] = False
            salvar_estado(estado)
            time.sleep(RECONNECT_DELAY_S)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[gps] encerrado pelo usuário.")
