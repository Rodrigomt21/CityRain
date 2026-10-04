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

Auditoria retroativa de uma sessão já encerrada (J6), incluindo pastas fora
da Jetson (ex.: cópia de campo trazida pro PC do Rodrigo):
    python3 verifica_teste_campo.py --frames-dir PASTA --fim "AAAA-MM-DD HH:MM" "AAAA-MM-DD HH:MM"
"""

import json
import os
import statistics
import subprocess
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

FRAMES_DIR = "/home/jetson/frames"
GAP_MAXIMO_S = 2.5  # acima disso, conta como possível queda da câmera

# Abaixo do menor reboot já observado em campo (~44s de corte+boot, ver
# Apêndice A da spec) não é corte de energia — é soluço normal de
# câmera/USB, que já é coberto por GAP_MAXIMO_S com outro significado.
CORTE_GAP_MINIMO_S = 30


def parse_datetime_str(texto: str) -> Optional[datetime]:
    """Tenta os formatos aceitos; devolve None (não levanta) se nenhum bater
    — quem chama decide se isso é erro fatal ou um argumento opcional."""
    for formato in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%H:%M:%S", "%H:%M"):
        try:
            dt = datetime.strptime(texto, formato)
        except ValueError:
            continue
        if formato.startswith("%H"):
            hoje = datetime.now()
            dt = dt.replace(year=hoje.year, month=hoje.month, day=hoje.day)
        return dt
    return None


def parse_datetime_obrigatorio(texto: str) -> datetime:
    dt = parse_datetime_str(texto)
    if dt is None:
        print(f"Não consegui entender o horário {texto!r}. Use 'AAAA-MM-DD HH:MM' ou 'HH:MM'.")
        sys.exit(1)
    return dt


def parse_inicio(args):
    if not args:
        return datetime.now() - timedelta(hours=6)
    return parse_datetime_obrigatorio(args[0])


def extrai_flag(argv: List[str], nome: str) -> Tuple[Optional[str], List[str]]:
    """Remove e devolve o valor de --nome VALOR ou --nome=VALOR de argv,
    junto com o argv restante (só os posicionais). Existe pra não trazer
    argparse pra um script que já vive de parsing manual simples."""
    valor = None
    restante = []
    i = 0
    prefixo = f"--{nome}"
    while i < len(argv):
        a = argv[i]
        if a == prefixo and i + 1 < len(argv):
            valor = argv[i + 1]
            i += 2
            continue
        if a.startswith(prefixo + "="):
            valor = a[len(prefixo) + 1:]
            i += 1
            continue
        restante.append(a)
        i += 1
    return valor, restante


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


def frames_da_janela(inicio, frames_dir=FRAMES_DIR, fim=None):
    """Lista (timestamp, nome) dos frames entre `inicio` e `fim` (opcional).

    `frames_dir` parametrizável e `fim` opcional existem por causa do J6:
    uma auditoria retroativa lê uma pasta que não é `/home/jetson/frames`
    (cópia trazida pro PC) e pode misturar mais de uma sessão — sem um
    limite superior, um corte de uma sessão vizinha contaminaria a
    contagem desta.
    """
    try:
        arquivos = os.listdir(frames_dir)
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
        if ts >= inicio and (fim is None or ts <= fim):
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


def par_invalido_simples(caminho_jpg: str, caminho_json: str) -> Optional[str]:
    """Mesmo critério do `par_invalido()` do uploader.py (J2), duplicado de
    propósito aqui: `uploader.py` importa `gate`, que só existe de verdade
    na Jetson (carrega o modelo treinado de ~/modelo_chuva) — importar
    `uploader.py` nesta auditoria quebraria o script em qualquer máquina
    que não seja a placa. A lógica é pequena o bastante para não valer esse
    acoplamento; se o critério de invalidez mudar em um lugar, mudar no
    outro também.
    """
    try:
        if os.path.getsize(caminho_jpg) == 0:
            return "jpg de 0 byte"
        if not os.path.exists(caminho_json):
            return "json ausente"
        if os.path.getsize(caminho_json) == 0:
            return "json de 0 byte"
        with open(caminho_jpg, "rb") as f:
            if f.read(3) != b"\xff\xd8\xff":
                return "jpg sem magic bytes de JPEG"
        with open(caminho_json) as f:
            json.load(f)
    except (ValueError, OSError) as e:
        return f"ilegivel: {e}"
    return None


def detecta_cortes_por_gap(
    frames_ordenados: List[Tuple[datetime, str]], gap_minimo_s: float = CORTE_GAP_MINIMO_S
) -> List[Tuple[datetime, datetime, float]]:
    """Gaps grandes o bastante pra só serem corte de energia + reboot, não
    soluço de câmera/USB.

    Existe porque a sessão de 23/09 (e qualquer sessão antiga) não tinha
    `sessao.service`/`boots.csv` rodando ainda — a única evidência
    disponível pra reconstruí-la retroativamente são os próprios
    timestamps no nome dos arquivos. Uma vez que `sessao.service` esteja
    deployado, `le_boots_csv()` (ver sessao.py) é a fonte melhor pra
    sessões novas; isto aqui continua valendo pra auditar dado histórico.
    """
    gaps = []
    for (t_anterior, _), (t_atual, _) in zip(frames_ordenados, frames_ordenados[1:]):
        delta = (t_atual - t_anterior).total_seconds()
        if delta >= gap_minimo_s:
            gaps.append((t_anterior, t_atual, delta))
    return gaps


def cadencia_mediana(
    frames_ordenados: List[Tuple[datetime, str]], gap_minimo_s: float = CORTE_GAP_MINIMO_S
) -> Optional[float]:
    """Mediana dos deltas entre frames consecutivos que NÃO são corte
    (delta < `gap_minimo_s`).

    Existe pra estimar quantos frames a sessão teria produzido se nenhum
    corte tivesse acontecido — sem cravar 1,00s: a câmera + `fsync` + SSD
    USB 2.0 desta placa produz uma cadência real um pouco acima disso (medi
    ~1,02s/frame na sessão de 23/09, ver Apêndice A da spec). Usa a mediana,
    não a média, pra um único delta grande que escapou do filtro de corte
    (ex.: 29,9s, logo abaixo do limiar) não distorcer a estimativa.
    Devolve None se não houver nenhum delta "normal" pra medir (sessão com
    0 ou 1 frame, ou 100% dela feita de corte).
    """
    deltas_normais = []
    for (t_anterior, _), (t_atual, _) in zip(frames_ordenados, frames_ordenados[1:]):
        delta = (t_atual - t_anterior).total_seconds()
        if delta < gap_minimo_s:
            deltas_normais.append(delta)
    if not deltas_normais:
        return None
    return statistics.median(deltas_normais)


def resumo_sessao(inicio: datetime, frames_dir: str = FRAMES_DIR, fim: Optional[datetime] = None) -> Dict:
    """Resumo por sessão pedido pelo J6: frames capturados, pares
    inválidos, cortes detectados, tempo parado e o **rendimento ponta a
    ponta** — que é o número a citar (ver Apêndice A da spec), não a taxa
    de perda.

    A taxa de perda (`pares_invalidos / frames_capturados`) só compara com
    o que FOI escrito — ela ignora o tempo inteiro que a placa passou
    desligada/rebotando sem escrever frame nenhum, e por isso subestima o
    prejuízo. Uma sessão pode ter taxa de perda baixa e rendimento péssimo
    se a maior parte do tempo foi gasta rebotando: os poucos frames
    escritos podem estar quase todos íntegros. Foi exatamente o caso de
    23/09: 20,7% de perda, mas só 23,8% de rendimento — a placa passou 72%
    da sessão parada.

    `fim` delimita a janela quando a pasta mistura mais de uma sessão (ex.:
    cópia de campo com vários dias de coleta) — sem isso, um corte ou par
    inválido de uma sessão vizinha contaminaria a contagem desta.
    """
    frames = frames_da_janela(inicio, frames_dir=frames_dir, fim=fim)
    total = len(frames)

    invalidos = []
    for _, nome_jpg in frames:
        caminho_jpg = os.path.join(frames_dir, nome_jpg)
        caminho_json = os.path.join(frames_dir, nome_jpg[: -len(".jpg")] + ".json")
        motivo = par_invalido_simples(caminho_jpg, caminho_json)
        if motivo:
            invalidos.append((nome_jpg, motivo))
    validos = total - len(invalidos)

    cortes = detecta_cortes_por_gap(frames)
    tempo_parado_s = sum(delta for _, _, delta in cortes)

    duracao_sessao_s = (frames[-1][0] - frames[0][0]).total_seconds() if total >= 2 else 0.0
    fracao_parada = (tempo_parado_s / duracao_sessao_s) if duracao_sessao_s else 0.0

    cadencia_s = cadencia_mediana(frames)
    frames_possiveis = (duracao_sessao_s / cadencia_s) if cadencia_s else None
    rendimento_ponta_a_ponta = (validos / frames_possiveis) if frames_possiveis else None

    taxa_perda = (len(invalidos) / total) if total else 0.0

    return {
        "frames_capturados": total,
        "frames_validos": validos,
        "pares_invalidos": len(invalidos),
        "invalidos_detalhe": invalidos,
        "cortes_detectados": len(cortes),
        "cortes_detalhe": cortes,
        "duracao_sessao_s": duracao_sessao_s,
        "tempo_parado_s": tempo_parado_s,
        "fracao_parada": fracao_parada,
        "cadencia_mediana_s": cadencia_s,
        "frames_possiveis": frames_possiveis,
        "rendimento_ponta_a_ponta": rendimento_ponta_a_ponta,
        "taxa_perda": taxa_perda,
    }


def secao_resumo_sessao(inicio: datetime, frames_dir: str = FRAMES_DIR, fim: Optional[datetime] = None) -> Dict:
    print("\n== Resumo da sessão (J6) ==")
    resumo = resumo_sessao(inicio, frames_dir=frames_dir, fim=fim)
    print(f"  Frames escritos: {resumo['frames_capturados']} "
          f"({resumo['frames_validos']} válidos, {resumo['pares_invalidos']} inválidos)")
    print(f"  Cortes de energia detectados (gap ≥ {CORTE_GAP_MINIMO_S}s): {resumo['cortes_detectados']}")
    for t_anterior, t_atual, delta in resumo["cortes_detalhe"]:
        print(f"    {t_anterior:%H:%M:%S} → {t_atual:%H:%M:%S}  (corte de {delta:.0f}s)")
    if resumo["duracao_sessao_s"]:
        print(f"  Tempo parado: {resumo['tempo_parado_s']:.0f}s de {resumo['duracao_sessao_s']:.0f}s "
              f"da sessão ({resumo['fracao_parada']:.0%})")
    if resumo["cadencia_mediana_s"] is not None:
        print(f"  Cadência observada: {resumo['cadencia_mediana_s']:.3f}s/frame "
              f"⇒ ~{resumo['frames_possiveis']:.0f} frames possíveis sem corte")
    print(f"  Taxa de perda (só entre os frames escritos, subestima o prejuízo): {resumo['taxa_perda']:.1%}")
    if resumo["rendimento_ponta_a_ponta"] is not None:
        print(f"  >>> RENDIMENTO PONTA A PONTA (válidos / possíveis sem corte): "
              f"{resumo['rendimento_ponta_a_ponta']:.1%} <<<  — este é o número a citar")
    return resumo


def main():
    argv = sys.argv[1:]
    frames_dir_arg, argv = extrai_flag(argv, "frames-dir")
    fim_arg, argv = extrai_flag(argv, "fim")

    inicio = parse_inicio(argv)
    fim = parse_datetime_obrigatorio(fim_arg) if fim_arg else None
    frames_dir = frames_dir_arg or FRAMES_DIR

    cabecalho = f"Auditando trajeto desde {inicio:%Y-%m-%d %H:%M:%S}"
    if fim:
        cabecalho += f" até {fim:%Y-%m-%d %H:%M:%S}"
    print(cabecalho)

    secao_citycam(inicio)
    frames = secao_frames(inicio)
    secao_metadados(frames)
    secao_uploader(inicio)
    secao_wifi_watchdog(inicio)
    secao_disco(inicio)
    secao_resumo_sessao(inicio, frames_dir=frames_dir, fim=fim)


if __name__ == "__main__":
    main()
