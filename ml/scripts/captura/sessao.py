#!/usr/bin/env python3
"""
sessao.py — Diagnóstico de boot para o CityRain (J6).

Hoje a diferença entre "a energia caiu" e "alguém apertou o botão" só é
descoberta cruzando arquivos de 0 byte com o `wtmp` e com `orphan inode` do
ext4 — arqueologia manual que não escala para uma temporada de coleta
inteira. A informação já existe no sistema e é barata: este script só
precisa lê-la e registrá-la a cada boot, para que a pergunta seja
respondida sozinha no boot seguinte.

Mecanismo (ver docs/specs/spec-pipeline-jetson.md, seção J6):
  - No arranque (`sessao.py boot`): grava uma linha em `boots.csv` com a
    hora do sistema, a hora do GPS (segunda fonte, ver módulo docstring
    abaixo sobre RTC), se o marcador `aberta` da sessão anterior ainda
    existia (⇒ a sessão anterior não terminou de forma ordenada ⇒ crash),
    e a contagem de `orphan inodes` do `dmesg` deste boot. Em seguida cria
    o marcador de novo, para a checagem do PRÓXIMO boot.
  - No desligamento (`sessao.py stop`, via `ExecStop` do `sessao.service`):
    remove o marcador. Isso só roda num desligamento ordenado (botão,
    `systemctl stop`, ou o `shutdown` normal do sistema) — um corte de
    energia real nunca chega a executar o `ExecStop`, e é exatamente essa
    ausência que denuncia o corte no boot seguinte.

Não confie no timestamp do sistema como identificador de sessão: esta placa
não tem RTC utilizável (`hwclock -r` falha), o relógio no boot vem do
`fake-hwclock` (última hora salva antes de desligar) e só é corrigido pelo
NTP quando há rede. Foi medido nesta placa `ExecMainStartTimestamp` de um
boot com 5 dias de atraso em relação ao horário real (ver Apêndice A da
spec) — por isso a hora do GPS (`gps.hora_rmc_utc`, vinda da constelação,
independente do relógio local) é gravada como segunda fonte sempre que
houver fix.

Rodar como serviço (sessao.service) ou manualmente:
    python3 sessao.py boot   # ExecStart
    python3 sessao.py stop   # ExecStop
"""

import csv
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from typing import Callable, List, Optional, Tuple

# ============================================================
# Caminhos padrão (produção). Todas as funções que os usam recebem o
# caminho como parâmetro com este valor como default — nunca como
# constante fixa usada direto no corpo da função — para que os testes
# possam apontar para um tmp_path sem tocar em nada da Jetson real.
# ============================================================
FRAMES_DIR_PADRAO = "/home/jetson/frames"
SESSAO_DIR_PADRAO = os.path.join(FRAMES_DIR_PADRAO, "sessao")
CSV_NOME_PADRAO = "boots.csv"
MARCADOR_NOME = "aberta"
GPS_ESTADO_PATH_PADRAO = "/run/cityrain/gps.json"

CSV_CAMPOS = [
    "boot_utc_sistema",
    "boot_utc_gps",
    "marcador_sessao_anterior",
    "tipo",
    "orphan_inodes",
    "wtmp_ultimo_evento",
]


# ============================================================
# Parsing puro — recebe texto, nunca chama subprocess diretamente.
# Testável com as amostras reais desta placa sem precisar estar nela.
# ============================================================

def conta_orphan_inodes(texto_dmesg: str) -> int:
    """Soma as ocorrências de 'EXT4-fs (sda1): N orphan inodes deleted'.

    Amostra real desta placa (ver spec, Apêndice A):
        EXT4-fs (sda1): 11 orphan inodes deleted
        EXT4-fs (sda1): recovery complete

    N > 0 é a assinatura de journal replay depois de um corte de energia:
    o ext4 encontrou inodes que tinham sido apagados/truncados mas cujo
    metadado não chegou a ser persistido antes da queda, e os limpou no
    replay do journal. Quem chama passa só o texto do `dmesg` referente ao
    boot atual — este parser não sabe (nem precisa saber) delimitar boots.
    """
    total = 0
    for linha in texto_dmesg.splitlines():
        m = re.search(r"(\d+)\s+orphan inodes deleted", linha)
        if m:
            total += int(m.group(1))
    return total


def ultimo_evento_wtmp(texto_wtmp: str) -> Optional[str]:
    """Classifica o desligamento mais recente registrado no `wtmp`.

    Espera a saída do `last -x` (mais recente primeiro). Amostra real desta
    placa (ver spec):
        jetson   :0   :0   Wed Sep 23 09:49 - crash  (-9762+11:49)
        runlevel (to lvl 5)   4.9.299-tegra    Tue Sep 15 22:23 - 09:50 (7+11:26)
        shutdown system down  4.9.299-tegra    Tue Sep 15 22:23 - 23:00 (-9755+00:22)

    Só o TIPO do evento importa — nunca a hora que a linha registra: sem
    RTC, os timestamps do próprio `last` podem estar errados (relógio
    pré-NTP), então usar essa hora para decidir qualquer coisa seria trocar
    um problema por outro. Serve como corroboração do marcador de sessão
    (a fonte primária), não como substituto dele: `last` pode não estar
    disponível ou o wtmp pode ter girado.
    """
    for linha in texto_wtmp.splitlines():
        if "shutdown system down" in linha:
            return "limpo"
        if re.search(r"-\s*crash\b", linha):
            return "crash"
        if re.search(r"-\s*down\b", linha):
            return "limpo"
    return None


def le_hora_gps(gps_json_path: str = GPS_ESTADO_PATH_PADRAO) -> Optional[str]:
    """Lê `hora_rmc_utc` do último estado salvo pelo gps.service.

    Devolve None (não levanta) em qualquer um destes casos, todos normais
    em campo: arquivo ainda não existe (gps.service não subiu ainda),
    schema antigo sem o campo (ver J7 — ainda não deployado em toda
    sessão), ou sem fix no momento do boot. A ausência é dado, não erro: a
    linha do CSV registra a coluna vazia em vez de quebrar o registro
    inteiro.
    """
    try:
        with open(gps_json_path) as f:
            estado = json.load(f)
    except (FileNotFoundError, ValueError, OSError):
        return None
    return estado.get("hora_rmc_utc")


def le_dmesg(comando: Tuple[str, ...] = ("dmesg",)) -> str:
    """Executa `dmesg` de verdade. Isolado numa função substituível em
    teste — não há `dmesg` de Jetson fora da Jetson."""
    try:
        saida = subprocess.check_output(list(comando), stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        return ""
    return saida.decode(errors="replace")


def le_wtmp(comando: Tuple[str, ...] = ("last", "-x")) -> str:
    """Executa `last -x` de verdade. Isolado pelo mesmo motivo do
    `le_dmesg` acima."""
    try:
        saida = subprocess.check_output(list(comando), stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        return ""
    return saida.decode(errors="replace")


# ============================================================
# Marcador de sessão aberta
# ============================================================

def caminho_marcador(sessao_dir: str) -> str:
    return os.path.join(sessao_dir, MARCADOR_NOME)


def marcador_existe(sessao_dir: str) -> bool:
    return os.path.exists(caminho_marcador(sessao_dir))


def _fsync_arquivo(f) -> None:
    """Garante que o conteúdo já escrito está fisicamente no disco — sem
    isso, um corte de energia logo após o boot poderia perder a própria
    linha que prova que o boot aconteceu (mesma lição do J1)."""
    f.flush()
    os.fsync(f.fileno())


def _fsync_diretorio(caminho_dir: str) -> None:
    """O `rename`/`create` de um arquivo é metadado de diretório e também
    pode se perder num corte — mesmo padrão do `_fsync_diretorio` do J1."""
    fd = os.open(caminho_dir, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def cria_marcador(sessao_dir: str) -> None:
    """Cria (ou recria) o marcador da sessão em curso. O conteúdo em si não
    importa — é a EXISTÊNCIA do arquivo que o próximo boot verifica —, mas
    grava a hora por conveniência de inspeção manual."""
    os.makedirs(sessao_dir, exist_ok=True)
    caminho = caminho_marcador(sessao_dir)
    tmp = caminho + ".tmp"
    with open(tmp, "w") as f:
        f.write(datetime.now(timezone.utc).isoformat())
        _fsync_arquivo(f)
    os.replace(tmp, caminho)
    _fsync_diretorio(sessao_dir)


def remove_marcador(sessao_dir: str) -> None:
    """Chamado pelo `ExecStop`: um desligamento ordenado remove o marcador
    antes de a placa desligar de verdade. Se isto NUNCA rodar (corte de
    energia), o marcador sobrevive, e é essa sobrevivência que o próximo
    boot lê como prova de crash."""
    try:
        os.remove(caminho_marcador(sessao_dir))
    except FileNotFoundError:
        pass
    if os.path.isdir(sessao_dir):
        _fsync_diretorio(sessao_dir)


# ============================================================
# Registro em boots.csv (append-only)
# ============================================================

def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def registra_boot(
    sessao_dir: str = SESSAO_DIR_PADRAO,
    csv_nome: str = CSV_NOME_PADRAO,
    gps_json_path: str = GPS_ESTADO_PATH_PADRAO,
    dmesg_fn: Callable[[], str] = le_dmesg,
    wtmp_fn: Callable[[], str] = le_wtmp,
    agora_fn: Callable[[], datetime] = _agora_utc,
) -> dict:
    """Registra uma linha de boot em `boots.csv` e recria o marcador.

    A ordem importa: primeiro LÊ se o marcador da sessão anterior existia
    (isso decide `tipo`), só depois recria o marcador para a sessão que
    está começando agora. Todas as fontes são injetáveis (`dmesg_fn`,
    `wtmp_fn`, `agora_fn`, os caminhos) para que o teste rode inteiro sem
    tocar em `dmesg`/`last`/relógio real.
    """
    os.makedirs(sessao_dir, exist_ok=True)
    caminho_csv = os.path.join(sessao_dir, csv_nome)

    marcador_havia = marcador_existe(sessao_dir)
    # Marcador sobrevivente = a sessão anterior nunca chegou ao ExecStop
    # (nem por botão, nem por `systemctl stop`) ⇒ só um corte de energia
    # explica isso. Ausência de marcador é o caso comum: ou a sessão
    # anterior desligou de forma ordenada, ou este é o primeiro boot.
    tipo = "crash" if marcador_havia else "limpo"

    orphan_inodes = conta_orphan_inodes(dmesg_fn())
    wtmp_evento = ultimo_evento_wtmp(wtmp_fn())
    hora_gps = le_hora_gps(gps_json_path)

    linha = {
        "boot_utc_sistema": agora_fn().isoformat(),
        "boot_utc_gps": hora_gps or "",
        "marcador_sessao_anterior": "true" if marcador_havia else "false",
        "tipo": tipo,
        "orphan_inodes": str(orphan_inodes),
        "wtmp_ultimo_evento": wtmp_evento or "",
    }

    novo = not os.path.exists(caminho_csv)
    with open(caminho_csv, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_CAMPOS)
        if novo:
            writer.writeheader()
        writer.writerow(linha)
        _fsync_arquivo(f)
    _fsync_diretorio(sessao_dir)

    cria_marcador(sessao_dir)
    return linha


def le_boots_csv(sessao_dir: str = SESSAO_DIR_PADRAO, csv_nome: str = CSV_NOME_PADRAO) -> List[dict]:
    """Lê o histórico completo de boots já registrados, do mais antigo pro
    mais novo. Usado por `verifica_teste_campo.py` para cruzar sessões com
    o número de cortes já conhecido pelo `sessao.service`."""
    caminho_csv = os.path.join(sessao_dir, csv_nome)
    try:
        with open(caminho_csv, newline="") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []


# ============================================================
# CLI — ExecStart chama "boot", ExecStop chama "stop"
# ============================================================

def main(argv: Optional[List[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    comando = argv[0] if argv else "boot"

    if comando == "boot":
        linha = registra_boot()
        print("[sessao] boot registrado: {}".format(linha))
        return 0
    if comando == "stop":
        remove_marcador(SESSAO_DIR_PADRAO)
        print("[sessao] marcador removido (desligamento ordenado)")
        return 0

    sys.stderr.write("uso: sessao.py [boot|stop]\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
