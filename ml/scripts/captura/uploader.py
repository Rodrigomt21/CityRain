#!/usr/bin/env python3
"""
uploader.py — Envia pares frame+metadado (gerados pelo captura.py) ao backend
do CityRain, com fila local e retry.

A fila é o próprio diretório ~/frames: cada par (frame_X.jpg, frame_X.json)
completo é candidato a upload. Só é apagado do disco depois de confirmação
HTTP 2xx do backend — enquanto isso não acontece, o dado de campo continua
seguro localmente, mesmo sem rede.

Rodar como serviço (uploader.service) ou manualmente: python3 uploader.py
Encerrar (modo manual): Ctrl+C
"""

import json
import os
import socket
import subprocess
import time

import requests

import gate

FRAMES_DIR = "/home/jetson/frames"
CONFIG_PATH = "/home/jetson/scripts/cityrain_config.json"
PASTA_SEM_CHUVA_PENDENTE_PADRAO = "/home/jetson/frames/sem_chuva_pendente"
PASTA_ERRO_GATE_PADRAO = "/home/jetson/frames/erro_gate"

CICLO_OCIOSO_S = 5       # sem nada na fila, espera isso antes de checar de novo
BACKOFF_INICIAL_S = 5
BACKOFF_MAX_S = 300
TIMEOUT_REQUEST_S = 30
TENTATIVAS_GATE_MAX = 5  # depois disso, quarentena — ver classifica()/move_para_erro_gate()


def carrega_config():
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    config.setdefault("device_id", socket.gethostname())
    config.setdefault("intervalo_amostragem_metered_s", 15)
    config.setdefault("conexoes_metered", [])
    config.setdefault("source_type", "jetson_nano")
    config.setdefault("limiar_chuva", 0.5)
    config.setdefault("pasta_sem_chuva_pendente", PASTA_SEM_CHUVA_PENDENTE_PADRAO)
    config.setdefault("pasta_erro_gate", PASTA_ERRO_GATE_PADRAO)
    return config


def carrega_metadado(caminho_json):
    with open(caminho_json) as f:
        return json.load(f)


def salva_metadado(caminho_json, metadado):
    """Mesmo padrão atômico do captura.py: tmp + os.replace."""
    tmp_path = caminho_json + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(metadado, f)
    os.replace(tmp_path, caminho_json)


def pares_pendentes():
    """Pares (jpg, json) completos, do mais antigo pro mais novo. A ordenação
    lexicográfica do nome já é cronológica (timestamp AAAAMMDD_HHMMSS_mmm no
    nome do arquivo), então um sort simples do nome basta."""
    try:
        arquivos = set(os.listdir(FRAMES_DIR))
    except FileNotFoundError:
        return []

    pares = []
    for nome in sorted(arquivos):
        if not nome.endswith(".json") or nome.endswith(".tmp"):
            continue
        nome_jpg = nome[: -len(".json")] + ".jpg"
        if nome_jpg in arquivos:
            pares.append((os.path.join(FRAMES_DIR, nome_jpg), os.path.join(FRAMES_DIR, nome)))
    return pares


def interface_default():
    """Interface de rede usada pela rota default agora (a de menor metric)."""
    try:
        saida = subprocess.check_output(
            ["ip", "route", "show", "default"], stderr=subprocess.DEVNULL
        ).decode()
    except (subprocess.CalledProcessError, OSError):
        return None

    melhor_iface, menor_metric = None, None
    for linha in saida.splitlines():
        partes = linha.split()
        if "dev" not in partes:
            continue
        iface = partes[partes.index("dev") + 1]
        metric = 0
        if "metric" in partes:
            try:
                metric = int(partes[partes.index("metric") + 1])
            except (ValueError, IndexError):
                metric = 0
        if menor_metric is None or metric < menor_metric:
            melhor_iface, menor_metric = iface, metric
    return melhor_iface


def conexao_da_interface(iface):
    """Nome do perfil NetworkManager (ex.: 'Rodrigo') associado à interface."""
    if not iface:
        return None
    try:
        saida = subprocess.check_output(
            ["nmcli", "-t", "-f", "DEVICE,NAME", "connection", "show", "--active"],
            stderr=subprocess.DEVNULL,
        ).decode()
    except (subprocess.CalledProcessError, OSError):
        return None

    for linha in saida.splitlines():
        dispositivo, _, nome = linha.partition(":")
        if dispositivo == iface:
            return nome
    return None


def rede_e_medida(config):
    """True quando a rota default de agora é uma das conexões marcadas como
    'metered' (ex.: hotspot do celular) — nesse caso o uploader amostra em
    vez de tentar drenar a fila inteira de uma vez."""
    nome_conexao = conexao_da_interface(interface_default())
    return nome_conexao in config["conexoes_metered"]


def classifica(caminho_jpg, caminho_json, metadado, config):
    """Roda o gate binário uma vez por frame e grava o resultado no .json
    local (weather_label/confidence), pra não reclassificar em cada retry —
    a inferência custa ~2s nesta Jetson, não é grátis repetir.

    O contador `tentativas_gate` é incrementado e salvo ANTES de chamar o
    gate de propósito: se o processo morrer no meio da inferência (crash
    nativo do torch/numpy — segfault não é exceção Python capturável), o
    contador já está em disco pra próxima tentativa saber que essa foto já
    falhou antes, mesmo sem nunca ter chegado ao `except` de ninguém."""
    if "weather_label" in metadado:
        return metadado

    metadado["tentativas_gate"] = metadado.get("tentativas_gate", 0) + 1
    salva_metadado(caminho_json, metadado)

    resultado = gate.classificar(caminho_jpg, config)
    metadado["weather_label"] = (
        "chuva" if resultado["classe"] == gate.CLASSE_COM_GOTA else "seco"
    )
    metadado["confidence"] = resultado["probabilidade"]
    salva_metadado(caminho_json, metadado)
    return metadado


def move_para_erro_gate(caminho_jpg, caminho_json, config):
    """Depois de TENTATIVAS_GATE_MAX falhas classificando o mesmo frame
    (imagem corrompida, modelo quebrado etc.), tira o par da frente da fila.

    Sem isso, um único frame problemático prende o uploader inteiro num
    crash-loop: Restart=always reinicia o serviço, e pares_pendentes()
    sempre devolve o mais antigo primeiro — ou seja, o mesmo frame ruim
    trava todo o resto atrás dele pra sempre. Nada é apagado, só isolado
    pra inspeção manual."""
    pasta = config.get("pasta_erro_gate", PASTA_ERRO_GATE_PADRAO)
    os.makedirs(pasta, exist_ok=True)
    for origem in (caminho_jpg, caminho_json):
        os.replace(origem, os.path.join(pasta, os.path.basename(origem)))


def move_para_pendente_seco(caminho_jpg, caminho_json, config):
    """'Seco' ainda não tem endpoint no backend (ver
    MUDANCAS_NECESSARIAS_BACKEND.md, item 1: falta um jeito de avisar 'sem
    chuva' sem subir foto, ou tornar `image` opcional no /ingest). Em vez de
    enviar ou apagar, tira o par da fila principal e guarda aqui — nada se
    perde, só para de competir com a fila de reenvio até a decisão do
    Guilherme. Quando o endpoint existir, é só trocar esta função por uma
    chamada de verdade."""
    pasta = config.get("pasta_sem_chuva_pendente", PASTA_SEM_CHUVA_PENDENTE_PADRAO)
    os.makedirs(pasta, exist_ok=True)
    for origem in (caminho_jpg, caminho_json):
        os.replace(origem, os.path.join(pasta, os.path.basename(origem)))


def envia_par(caminho_jpg, metadado, config):
    """Monta o metadata no formato achatado do contrato real (captured_at/
    latitude/longitude/source_type/weather_label/confidence) — ver
    CONTRATO_API.md. `gps` local pode não ter fix; nesse caso latitude/
    longitude vão como None (ainda não confirmado com o Guilherme se o
    backend aceita nulo aqui, ver MUDANCAS_NECESSARIAS_BACKEND.md)."""
    gps = metadado.get("gps") or {}
    payload = {
        "captured_at": metadado.get("capturado_em_utc"),
        "latitude": gps.get("latitude"),
        "longitude": gps.get("longitude"),
        "source_type": config.get("source_type", "jetson_nano"),
        "weather_label": metadado["weather_label"],
        "confidence": metadado["confidence"],
    }

    headers = {}
    if config.get("token"):
        headers["Authorization"] = f"Bearer {config['token']}"

    with open(caminho_jpg, "rb") as img:
        return requests.post(
            config["backend_url"],
            headers=headers,
            files={"image": (os.path.basename(caminho_jpg), img, "image/jpeg")},
            data={"metadata": json.dumps(payload)},
            timeout=TIMEOUT_REQUEST_S,
        )


def apaga_par(caminho_jpg, caminho_json):
    for caminho in (caminho_jpg, caminho_json):
        try:
            os.remove(caminho)
        except FileNotFoundError:
            pass


def main():
    config = carrega_config()
    backoff = BACKOFF_INICIAL_S

    while True:
        pares = pares_pendentes()
        if not pares:
            time.sleep(CICLO_OCIOSO_S)
            continue

        medida = rede_e_medida(config)
        # Em rede medida (hotspot), manda só o item mais recente por ciclo —
        # o resto espera uma rede ilimitada aparecer pra drenar em lote.
        lote = [pares[-1]] if medida else pares

        deu_erro = False
        for caminho_jpg, caminho_json in lote:
            metadado = carrega_metadado(caminho_json)

            if metadado.get("tentativas_gate", 0) >= TENTATIVAS_GATE_MAX:
                print(
                    f"[uploader] {caminho_jpg} excedeu {TENTATIVAS_GATE_MAX} tentativas "
                    f"de classificação — movendo pra quarentena ({PASTA_ERRO_GATE_PADRAO})"
                )
                move_para_erro_gate(caminho_jpg, caminho_json, config)
                continue

            try:
                metadado = classifica(caminho_jpg, caminho_json, metadado, config)
            except Exception as e:
                print(f"[uploader] falha classificando {caminho_jpg} no gate: {e}")
                deu_erro = True
                break

            if metadado["weather_label"] == "seco":
                move_para_pendente_seco(caminho_jpg, caminho_json, config)
                continue

            try:
                resposta = envia_par(caminho_jpg, metadado, config)
            except requests.RequestException as e:
                print(f"[uploader] falha de rede enviando {caminho_jpg}: {e}")
                deu_erro = True
                break

            if 200 <= resposta.status_code < 300:
                apaga_par(caminho_jpg, caminho_json)
                backoff = BACKOFF_INICIAL_S
            elif 400 <= resposta.status_code < 500:
                print(
                    f"[uploader] backend rejeitou {caminho_jpg} "
                    f"(HTTP {resposta.status_code}): {resposta.text[:200]!r} — "
                    f"mantendo na fila, checar contrato da API"
                )
                deu_erro = True
                break
            else:
                print(f"[uploader] erro no backend enviando {caminho_jpg} (HTTP {resposta.status_code})")
                deu_erro = True
                break

        if deu_erro:
            time.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX_S)
        elif medida:
            time.sleep(config["intervalo_amostragem_metered_s"])


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[uploader] encerrado pelo usuário.")
