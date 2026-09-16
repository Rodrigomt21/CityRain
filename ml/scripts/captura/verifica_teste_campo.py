#!/usr/bin/env python3
"""
verifica_teste_campo.py — Auditoria pós-trajeto do pipeline de captura.

Roda DEPOIS do carro voltar pro alcance de rede (não precisa de tela/teclado
durante o trajeto — citycam/uploader/wifi-watchdog já rodam headless via
systemd). Recebe o horário de início do trajeto e resume o que aconteceu:
reinícios do citycam (câmera caindo com vibração), continuidade dos frames
capturados, presença do metadado .json, comportamento do uploader e do
wifi-watchdog, e a guarda de espaço em disco.

Uso:
    python3 verifica_teste_campo.py "2026-07-30 08:00"
    python3 verifica_teste_campo.py 08:00        # assume o dia de hoje
    python3 verifica_teste_campo.py               # assume as últimas 6h
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta

FRAMES_DIR = "/home/jetson/frames"
GAP_MAXIMO_S = 2.5  # acima disso, conta como possível queda da câmera


def parse_inicio(args):
    if not args:
        return datetime.now() - timedelta(hours=6)
    texto = args[0]
    for formato in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%H:%M:%S", "%H:%M"):
        try:
            dt = datetime.strptime(texto, formato)
        except ValueError:
            continue
        if formato.startswith("%H"):
            hoje = datetime.now()
            dt = dt.replace(year=hoje.year, month=hoje.month, day=hoje.day)
        return dt
    print(f"Não consegui entender o horário {texto!r}. Use 'AAAA-MM-DD HH:MM' ou 'HH:MM'.")
    sys.exit(1)


def journal_desde(unidade, inicio):
    try:
        saida = subprocess.check_output(
            ["journalctl", "-u", unidade, "--since", inicio.strftime("%Y-%m-%d %H:%M:%S"), "--no-pager"],
            stderr=subprocess.DEVNULL,
        ).decode(errors="replace")
    except (subprocess.CalledProcessError, OSError):
        return []
    return saida.splitlines()


def parse_timestamp_frame(nome):
    """'frame_20260730_080512_123.jpg' -> datetime(2026,7,30,8,5,12,123000)."""
    stem = nome[len("frame_"):-len(".jpg")]
    data_str, hora_str, ms_str = stem.split("_")
    dt = datetime.strptime(data_str + hora_str, "%Y%m%d%H%M%S")
    return dt.replace(microsecond=int(ms_str) * 1000)


def frames_da_janela(inicio):
    try:
        arquivos = os.listdir(FRAMES_DIR)
    except FileNotFoundError:
        return []
    frames = []
    for nome in arquivos:
        if not nome.startswith("frame_") or not nome.endswith(".jpg"):
            continue
        try:
            ts = parse_timestamp_frame(nome)
        except ValueError:
            continue
        if ts >= inicio:
            frames.append((ts, nome))
    frames.sort()
    return frames


def secao_citycam(inicio):
    print("\n== citycam.service (captura de frames) ==")
    linhas = journal_desde("citycam.service", inicio)
    inicios = [l for l in linhas if "Started" in l or "Starting" in l]
    erros_camera = [l for l in linhas if "não foi possível abrir a câmera" in l]
    falhas_leitura = [l for l in linhas if "Falha na leitura do frame" in l]
    print(f"  Reinícios do serviço no período: {max(len(inicios) - 1, 0)}")
    if erros_camera:
        print(f"  ⚠️ {len(erros_camera)}x câmera não abriu (possível queda por vibração/USB)")
    if falhas_leitura:
        print(f"  ⚠️ {len(falhas_leitura)}x falha ao ler frame (câmera respondeu mas sem imagem)")
    if not erros_camera and not falhas_leitura and len(inicios) <= 1:
        print("  Nenhum reinício/erro detectado — serviço estável durante o trajeto.")


def secao_frames(inicio):
    print("\n== Continuidade dos frames (~/frames) ==")
    frames = frames_da_janela(inicio)
    if not frames:
        print("  Nenhum frame encontrado nessa janela — confira se o citycam.service "
              "chegou a rodar com a câmera conectada.")
        return frames

    duracao_s = (frames[-1][0] - frames[0][0]).total_seconds()
    print(f"  {len(frames)} frames entre {frames[0][0]:%H:%M:%S} e {frames[-1][0]:%H:%M:%S} "
          f"({duracao_s:.0f}s de janela)")

    gaps = []
    for (t_anterior, _), (t_atual, nome_atual) in zip(frames, frames[1:]):
        delta = (t_atual - t_anterior).total_seconds()
        if delta > GAP_MAXIMO_S:
            gaps.append((t_anterior, t_atual, delta))

    if gaps:
        print(f"  ⚠️ {len(gaps)} gap(s) > {GAP_MAXIMO_S}s (possível câmera caindo OU frame já "
              f"enviado e apagado pelo uploader — normal em rede não-medida, raro em hotspot):")
        for t_ini, t_fim, delta in gaps[:15]:
            print(f"    {t_ini:%H:%M:%S} → {t_fim:%H:%M:%S}  ({delta:.1f}s)")
        if len(gaps) > 15:
            print(f"    ... e mais {len(gaps) - 15}")
    else:
        print("  Sem gaps relevantes — captura contínua a ~1fps confirmada.")
    return frames


def secao_metadados(frames):
    print("\n== Metadado por frame (.json + GPS) ==")
    if not frames:
        return
    com_json, sem_json = 0, 0
    fix_true = fix_false = fix_null = 0
    for _, nome_jpg in frames:
        caminho_json = os.path.join(FRAMES_DIR, nome_jpg[:-len(".jpg")] + ".json")
        try:
            with open(caminho_json) as f:
                metadado = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            sem_json += 1
            continue
        com_json += 1
        gps = metadado.get("gps")
        if gps is None:
            fix_null += 1
        elif gps.get("fix"):
            fix_true += 1
        else:
            fix_false += 1

    print(f"  {com_json}/{len(frames)} frames com .json presente ainda no disco")
    if sem_json:
        print(f"  ({sem_json} sem .json no disco agora — provavelmente já enviados e "
              f"apagados pelo uploader, não é erro)")
    print(f"  GPS: fix=true em {fix_true}, fix=false em {fix_false}, sem gps.service (null) em {fix_null}")
    if fix_null == com_json:
        print("  Lembrete: fiação física do NEO-6M em /dev/ttyTHS1 ainda pendente — "
              "null aqui é esperado até isso ser feito.")


def secao_uploader(inicio):
    print("\n== uploader.service ==")
    linhas = journal_desde("uploader.service", inicio)
    falhas_rede = [l for l in linhas if "falha de rede" in l]
    rejeitados = [l for l in linhas if "rejeitou" in l]
    erros_backend = [l for l in linhas if "erro no backend" in l]
    print(f"  Falhas de rede: {len(falhas_rede)} | Rejeições 4xx (contrato): {len(rejeitados)} "
          f"| Erros 5xx/backend: {len(erros_backend)}")
    if rejeitados:
        print("  ⚠️ Backend rejeitou algum par (HTTP 4xx) — conferir CONTRATO_API.md / backend_url:")
        for l in rejeitados[:5]:
            print(f"    {l}")
    pendentes = [n for n in os.listdir(FRAMES_DIR) if n.endswith(".json")] if os.path.isdir(FRAMES_DIR) else []
    print(f"  Fila atual (pares ainda não enviados, de qualquer período): {len(pendentes)}")


def secao_wifi_watchdog(inicio):
    print("\n== wifi-watchdog.service (conectividade) ==")
    linhas = journal_desde("wifi-watchdog.service", inicio)
    reconexoes = [l for l in linhas if "reconectado" in l]
    resets = [l for l in linhas if "reiniciando a interface" in l]
    print(f"  Reconexões observadas: {len(reconexoes)} | Resets forçados do driver wlan0: {len(resets)}")
    if resets:
        print("  ⚠️ Precisou forçar down/up no wlan0 — sinal de instabilidade real do dongle/hotspot:")
        for l in resets:
            print(f"    {l}")


def secao_disco(inicio):
    print("\n== Guarda de espaço em disco ==")
    linhas = journal_desde("citycam.service", inicio)
    pausas = [l for l in linhas if "pausando gravação" in l]
    if pausas:
        print(f"  ⚠️ Disco ficou abaixo de 500MB livres {len(pausas)}x — gravação pausada no período.")
    else:
        print("  Não disparou — disco ficou acima de 500MB livres o trajeto todo.")
    livre_mb = None
    try:
        import shutil
        livre_mb = shutil.disk_usage(FRAMES_DIR).free / (1024 * 1024)
    except FileNotFoundError:
        pass
    if livre_mb is not None:
        print(f"  Espaço livre agora: {livre_mb:.0f}MB")


def main():
    inicio = parse_inicio(sys.argv[1:])
    print(f"Auditando trajeto desde {inicio:%Y-%m-%d %H:%M:%S}")

    secao_citycam(inicio)
    frames = secao_frames(inicio)
    secao_metadados(frames)
    secao_uploader(inicio)
    secao_wifi_watchdog(inicio)
    secao_disco(inicio)


if __name__ == "__main__":
    main()
