import Jetson.GPIO as GPIO
import time
import os
import sys

GPIO.setmode(GPIO.BOARD)
inPin = 13
GPIO.setup(inPin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

DEBOUNCE_S = 2.0             # tempo que o pino precisa ficar LOW sem soltar
INTERVALO_DEBOUNCE_S = 0.05  # frequência de checagem durante a confirmação

print("Monitor de botão iniciado. Aguardando pressão...")


def pressao_confirmada():
    """Só considera pressão de verdade se o pino ficar LOW ininterrupto por
    DEBOUNCE_S — evita desligar por ruído elétrico/vibração do carro, que
    pode gerar uma leitura LOW momentânea sem o botão ter sido apertado."""
    inicio = time.monotonic()
    while time.monotonic() - inicio < DEBOUNCE_S:
        if GPIO.input(inPin) == GPIO.HIGH:
            return False
        time.sleep(INTERVALO_DEBOUNCE_S)
    return True


try:
    while True:
        x = GPIO.input(inPin)
        if x == GPIO.LOW:
            if pressao_confirmada():
                print("Botão pressionado! Desligando...")
                GPIO.cleanup()  # limpa antes de desligar
                os.system("sudo /sbin/shutdown -h now")
                sys.exit(0)
            else:
                print("Leitura LOW momentânea (ruído?) — ignorando")
        time.sleep(0.2)
except Exception as e:
    print(f"Erro: {e}")
finally:
    GPIO.cleanup()
