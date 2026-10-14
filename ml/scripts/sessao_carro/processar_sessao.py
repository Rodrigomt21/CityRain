#!/usr/bin/env python3
"""Processa uma sessão de carro da Jetson: valida, normaliza, baixa CEMADEN e rotula.

Um comando transforma a pasta copiada da Jetson (jpg + json por frame) em frames
rotulados por pluviômetro, sem mexer no manifest global (`manifest_imt.csv`).
Reutiliza os scripts existentes, na mesma ordem usada nas sessões de 04/08 a 23/09:

  1. valida horário/GPS dos JSONs (% com fix, faixa de tempo, problemas de relógio);
  2. copia para `ml/data/raw/imt_coleta/<nome>/` e normaliza a orientação
     (`normalizar_orientacao.py`) para `ml/data/processed/imt_coleta/<nome>/`;
  3. baixa o CEMADEN/PED só dos dias (e estações perto da rota) que faltam no cache
     (`baixar_cemaden_ped.py`); para no primeiro HTTP 401 (a API limita a cota);
  4. rotula com `gerar_manifest.py` (mesmas regras de `rotulagem_imt.yaml`) e grava
     `ml/data/manifests/sessoes/manifest_<nome>.csv`;
  5. imprime o resumo por classe e por motivo de exclusão.

Uso:
    python ml/scripts/sessao_carro/processar_sessao.py /caminho/da/sessao
    python ml/scripts/sessao_carro/processar_sessao.py /caminho --dry-run      # nada escrito
    python ml/scripts/sessao_carro/processar_sessao.py /caminho --sem-rede     # só cache
    python ml/scripts/sessao_carro/processar_sessao.py /caminho --dia 2026-09-13
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import shutil
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = REPO / "ml/scripts"
CFG_NORMALIZACAO = REPO / "ml/configs/normalizacao_imt.yaml"
CFG_ROTULAGEM = REPO / "ml/configs/rotulagem_imt.yaml"
SAIDA_MANIFESTS = REPO / "ml/data/manifests/sessoes"

CLASSES = ("seco", "garoa", "moderada", "forte")
DATA_MINIMA_PLAUSIVEL = datetime(2026, 8, 1, tzinfo=timezone.utc)
OFFSET_LOCAL_H = 3                 # nome do arquivo é hora local (UTC-3)
TOL_NOME_ARQUIVO_S = 120           # tolerância nome x JSON
TOL_RELOGIO_RMC_S = 30             # tolerância relógio do sistema x hora do GPS
MARGEM_DOWNLOAD_MIN = 90           # janela_seco (60) + janela (15) + folga
RAIO_ESTACAO_KM = 5.0

MOTIVOS = {
    "sem_gps_fix": "sem posição GPS (e sem consenso seco da rede)",
    "posicao_desatualizada": "último fix GPS antigo demais (> 12 s)",
    "sem_estacao_no_raio": "nenhuma estação a <= 2 km",
    "sem_leitura_na_janela": "estação sem leitura na janela",
    "sem_consenso_regional": "estações próximas sem dado/discordam",
    "poucas_estacoes_consenso": "menos de 3 estações com dado na região",
    "seco_incerto": "estação zerada mas outra viu chuva em +-60 min",
    "zona_morta": "valor na fronteira entre classes",
    "sem_timestamp": "JSON sem horário válido",
}


def _carregar(nome: str, relativo: str):
    spec = importlib.util.spec_from_file_location(nome, SCRIPTS / relativo)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nome] = mod
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------
# Partes puras (testadas em ml/tests/test_sessao_carro.py)
# --------------------------------------------------------------------------

def parse_ts(texto: Any) -> datetime | None:
    """ISO-8601 (com Z ou offset) -> datetime UTC aware; None se inválido."""
    if not texto:
        return None
    try:
        dt = datetime.fromisoformat(str(texto).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def ts_do_nome(arquivo: str) -> datetime | None:
    """`frame_AAAAMMDD_HHMMSS_mmm.jpg` (hora local, UTC-3) -> datetime UTC."""
    partes = Path(arquivo).stem.split("_")
    if len(partes) < 3 or partes[0] != "frame":
        return None
    try:
        local = datetime.strptime(partes[1] + partes[2], "%Y%m%d%H%M%S")
    except ValueError:
        return None
    return (local + timedelta(hours=OFFSET_LOCAL_H)).replace(tzinfo=timezone.utc)


def validar_sessao(metas: list[dict], agora: datetime | None = None) -> dict:
    """Resume qualidade de horário e GPS dos JSONs de uma sessão.

    Args:
        metas: dicts lidos dos `frame_*.json`.
        agora: relógio de referência (injetável em testes).

    Returns:
        dict com contagens, faixa de tempo, dias UTC, % fix e lista `alertas`.
    """
    agora = agora or datetime.now(timezone.utc)
    n = len(metas)
    alertas: list[str] = []
    tss: list[datetime] = []
    sem_ts = com_fix = com_pos = 0
    nome_fora = rmc_n = rmc_fora = 0
    ordem_quebrada = 0
    anterior: datetime | None = None
    for m in metas:
        ts = parse_ts(m.get("capturado_em_utc"))
        gps = m.get("gps") or {}
        if gps.get("fix"):
            com_fix += 1
        if gps.get("latitude") is not None and gps.get("longitude") is not None:
            com_pos += 1
        if ts is None:
            sem_ts += 1
            continue
        tss.append(ts)
        if anterior is not None and ts < anterior:
            ordem_quebrada += 1
        anterior = ts
        t_nome = ts_do_nome(str(m.get("arquivo", "")))
        if t_nome is not None and abs((ts - t_nome).total_seconds()) > TOL_NOME_ARQUIVO_S:
            nome_fora += 1
        rmc = parse_ts(gps.get("hora_rmc_utc"))
        if rmc is not None:
            rmc_n += 1
            if abs((ts - rmc).total_seconds()) > TOL_RELOGIO_RMC_S:
                rmc_fora += 1

    pct_fix = 100.0 * com_fix / n if n else 0.0
    res: dict[str, Any] = {
        "n_frames": n, "sem_timestamp": sem_ts, "com_fix": com_fix,
        "com_posicao": com_pos, "pct_fix": pct_fix,
        "ts_min": min(tss) if tss else None, "ts_max": max(tss) if tss else None,
        "dias_utc": sorted({t.date().isoformat() for t in tss}),
        "com_hora_rmc": rmc_n, "relogio_fora_do_gps": rmc_fora,
        "nome_diverge_do_json": nome_fora, "alertas": alertas,
    }
    if n == 0:
        alertas.append("nenhum frame com JSON encontrado")
        return res
    if sem_ts:
        alertas.append(f"{sem_ts} JSON(s) sem horário válido (serão excluídos)")
    if tss and min(tss) < DATA_MINIMA_PLAUSIVEL:
        alertas.append(
            f"RELÓGIO: há horário anterior a {DATA_MINIMA_PLAUSIVEL.date()} "
            f"({min(tss).isoformat()}) — Jetson sem NTP/RTC; sessão inauditável")
    if tss and max(tss) > agora + timedelta(hours=1):
        alertas.append(f"RELÓGIO: horário no futuro ({max(tss).isoformat()})")
    if ordem_quebrada:
        alertas.append(f"RELÓGIO: {ordem_quebrada} salto(s) para trás no tempo")
    if nome_fora:
        alertas.append(
            f"RELÓGIO: {nome_fora} frame(s) com nome do arquivo != horário do JSON "
            f"(> {TOL_NOME_ARQUIVO_S}s, esperado UTC-3)")
    if rmc_fora:
        alertas.append(
            f"RELÓGIO: {rmc_fora}/{rmc_n} frame(s) com relógio do sistema > "
            f"{TOL_RELOGIO_RMC_S}s da hora do GPS")
    if rmc_n == 0 and com_fix:
        alertas.append("sem hora_rmc_utc nos JSONs: não dá para auditar o relógio")
    if com_fix == 0:
        alertas.append("NENHUM frame com GPS fix — só rotula seco por consenso da rede")
    elif pct_fix < 50:
        alertas.append(f"GPS fraco: só {pct_fix:.0f}% dos frames com fix")
    return res


def dias_necessarios(ts_min: datetime, ts_max: datetime,
                     margem_min: int = MARGEM_DOWNLOAD_MIN) -> list[str]:
    """Dias UTC (YYYY-MM-DD) a baixar, incluindo a margem das janelas de rótulo."""
    ini = (ts_min - timedelta(minutes=margem_min)).date()
    fim = (ts_max + timedelta(minutes=margem_min)).date()
    dias = []
    d = ini
    while d <= fim:
        dias.append(d.isoformat())
        d += timedelta(days=1)
    return dias


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância em km entre dois pontos (WGS84 esférico)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def estacoes_perto_da_rota(
    estacoes: dict[str, tuple[str, float, float]],
    pontos: list[tuple[float, float]],
    raio_km: float = RAIO_ESTACAO_KM,
) -> list[str]:
    """Códigos das estações a <= raio_km de qualquer ponto da rota.

    Pontos são reduzidos a uma grade de ~0,01 grau (~1 km) para ser barato.
    """
    grade = {(round(la, 2), round(lo, 2)) for la, lo in pontos}
    achadas = []
    for cod, (_n, la, lo) in estacoes.items():
        if any(haversine_km(la, lo, pl, po) <= raio_km + 1.0 for pl, po in grade):
            achadas.append(cod)
    return achadas


def pares_faltantes(codigos: list[str], dias: list[str], raw_dir: Path) -> list[tuple[str, str]]:
    """Pares (estação, dia) sem resposta em cache (nem dado, nem 'Nenhum resultado')."""
    faltam = []
    for dia in dias:
        for cod in codigos:
            dado = raw_dir / f"dados_pcd_{cod}_{dia}.json"
            if dado.exists() and dado.stat().st_size > 0:
                continue
            erro = raw_dir / f"ERRO_{cod}_{dia}.txt"
            if erro.exists() and "Nenhum resultado" in erro.read_text():
                continue
            faltam.append((cod, dia))
    return faltam


def resumir_manifest(linhas: list[dict]) -> dict:
    """Agrega linhas do manifest por evento: classes, exclusões por motivo."""
    eventos: dict[str, dict] = defaultdict(
        lambda: {"classes": Counter(), "motivos": Counter(), "total": 0})
    for r in linhas:
        ev = eventos[r["evento_id"]]
        ev["total"] += 1
        if r.get("classe"):
            ev["classes"][r["classe"]] += 1
        else:
            ev["motivos"][r.get("motivo_exclusao") or "desconhecido"] += 1
    return dict(eventos)


def formatar_resumo(eventos: dict) -> str:
    """Texto do resumo por evento/classe/motivo (ordenado, pronto para imprimir)."""
    out: list[str] = []
    total = Counter()
    total_mot = Counter()
    n_total = 0
    for ev in sorted(eventos):
        d = eventos[ev]
        rot = sum(d["classes"].values())
        n_total += d["total"]
        out.append(f"\n{ev}: {d['total']} frames, {rot} rotulados, "
                   f"{d['total'] - rot} sem rótulo")
        for c in CLASSES:
            out.append(f"    {c:<10}{d['classes'].get(c, 0):>7}")
            total[c] += d["classes"].get(c, 0)
        for mot, n in d["motivos"].most_common():
            out.append(f"    sem rótulo: {mot:<26}{n:>6}  {MOTIVOS.get(mot, '')}")
            total_mot[mot] += n
    rot_total = sum(total.values())
    out.append(f"\nTOTAL: {n_total} frames, {rot_total} rotulados "
               f"({100 * rot_total / n_total:.0f}%)" if n_total else "\nTOTAL: 0 frames")
    out.append("  " + "  ".join(f"{c}={total[c]}" for c in CLASSES))
    if total_mot:
        out.append("  sem rótulo: " + "  ".join(f"{m}={n}" for m, n in total_mot.most_common()))
    return "\n".join(out)


# --------------------------------------------------------------------------
# Efeitos colaterais
# --------------------------------------------------------------------------

def descobrir_frames(pasta: Path) -> tuple[list[Path], list[Path]]:
    """jpgs e jsons `frame_*` sob a pasta (recursivo, pois alguns dumps têm subpasta)."""
    jpgs = sorted(p for p in pasta.rglob("frame_*.jpg") if p.stat().st_size > 0)
    jsons = sorted(pasta.rglob("frame_*.json"))
    return jpgs, jsons


def baixar_faltantes(faltam: list[tuple[str, str]], ped) -> int:
    """Baixa os pares faltantes; para no primeiro HTTP 401 persistente. Retorna nº salvo."""
    email, senha = ped.carregar_credenciais()
    token = ped.obter_token(email, senha)
    ped.RAW_DIR.mkdir(parents=True, exist_ok=True)
    salvos = chamadas = 0
    for cod, dia in faltam:
        if chamadas and chamadas % 5 == 0:
            token = ped.obter_token(email, senha)
            time.sleep(1)
        params = {"codigo": cod, "inicio": f"{dia.replace('-', '')}0000",
                  "fim": f"{dia.replace('-', '')}2359", "rede": 11, "sensor": 10}
        status, body = ped._get(f"{ped.PED_BASE}/pcds/dados_pcd", params, token)
        chamadas += 1
        if status == 401:
            token = ped.obter_token(email, senha)
            status, body = ped._get(f"{ped.PED_BASE}/pcds/dados_pcd", params, token)
            chamadas += 1
            if status == 401:
                print(f"  HTTP 401 (cota do cadastro CEMADEN esgotada): PARANDO. "
                      f"{len(faltam) - salvos} par(es) ficam para depois.")
                break
        if status != 200:
            (ped.RAW_DIR / f"ERRO_{cod}_{dia}.txt").write_text(
                f"params={params}\nHTTP {status}\n{body[:2000]}")
            print(f"  [HTTP {status}] {cod} {dia}")
        else:
            (ped.RAW_DIR / f"dados_pcd_{cod}_{dia}.json").write_text(body)
            salvos += 1
            print(f"  [ok] {cod} {dia}")
        time.sleep(1)
    if salvos:
        n = ped.normalizar(sorted(ped.RAW_DIR.glob("dados_pcd_*")))
        print(f"  {n} leituras normalizadas -> {ped.OUT_CSV}")
    return salvos


def preparar_stage(jsons: list[Path], nome: str, dia: str | None, stage: Path) -> int:
    """Cria stage/<nome>/ com links só para os JSONs (opcionalmente de um único dia)."""
    destino = stage / nome
    destino.mkdir(parents=True)
    n = 0
    for j in jsons:
        if dia:
            try:
                ts = parse_ts(json.loads(j.read_text()).get("capturado_em_utc"))
            except (OSError, json.JSONDecodeError):
                continue
            if ts is None or ts.date().isoformat() != dia:
                continue
        (destino / j.name).symlink_to(j.resolve())
        n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pasta", type=Path, help="pasta da sessão copiada da Jetson (jpg + json)")
    ap.add_argument("--nome", help="nome da sessão (default: nome da pasta)")
    ap.add_argument("--dia", help="só frames deste dia UTC (YYYY-MM-DD)")
    ap.add_argument("--rotacao", type=int, default=180, choices=(0, 90, 180, 270),
                    help="rotação para o capô ficar embaixo (default 180, como nas 4 sessões)")
    ap.add_argument("--dry-run", action="store_true",
                    help="valida e rotula sem copiar, baixar nem escrever manifest")
    ap.add_argument("--sem-rede", action="store_true", help="não baixa CEMADEN (só cache)")
    ap.add_argument("--sem-normalizar", action="store_true", help="pula cópia/rotação dos jpgs")
    args = ap.parse_args(argv)

    pasta = args.pasta.resolve()
    if not pasta.is_dir():
        sys.exit(f"Pasta não encontrada: {pasta}")
    nome = args.nome or pasta.name

    # 1. validação -------------------------------------------------------
    jpgs, jsons = descobrir_frames(pasta)
    metas = []
    for j in jsons:
        try:
            metas.append(json.loads(j.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    if args.dia:
        metas = [m for m in metas
                 if (t := parse_ts(m.get("capturado_em_utc"))) and t.date().isoformat() == args.dia]
    v = validar_sessao(metas)
    orfaos_jpg = len({p.stem for p in jpgs} - {j.stem for j in jsons})
    print(f"== Sessão '{nome}' ({pasta})")
    print(f"Frames: {v['n_frames']} JSON, {len(jpgs)} jpg (jpg sem JSON: {orfaos_jpg})")
    print(f"GPS fix: {v['com_fix']}/{v['n_frames']} ({v['pct_fix']:.1f}%)  "
          f"| com posição: {v['com_posicao']}")
    if v["ts_min"]:
        print(f"Tempo UTC: {v['ts_min'].isoformat(timespec='seconds')} -> "
              f"{v['ts_max'].isoformat(timespec='seconds')}  dias: {', '.join(v['dias_utc'])}")
    print(f"hora_rmc_utc presente em {v['com_hora_rmc']} frames")
    for a in v["alertas"]:
        print(f"  ALERTA: {a}")
    if not v["n_frames"] or not v["ts_min"]:
        return 1

    # 2. normalização ----------------------------------------------------
    cfg_norm = yaml.safe_load(CFG_NORMALIZACAO.read_text())
    raw_dir = REPO / cfg_norm["raiz_entrada"] / nome
    proc_dir = REPO / cfg_norm["raiz_saida"] / nome
    if args.dry_run or args.sem_normalizar:
        print("\n[normalização pulada]" + (" (dry-run)" if args.dry_run else ""))
    else:
        norm = _carregar("normalizar_orientacao", "preprocessamento/normalizar_orientacao.py")
        raw_dir.mkdir(parents=True, exist_ok=True)
        for p in jpgs + jsons:
            alvo = raw_dir / p.name
            if not alvo.exists():
                shutil.copy2(p, alvo)
        rep = norm.process_pasta(
            nome=nome, cfg_entry={"rotacao_graus": args.rotacao},
            raiz_entrada=raw_dir.parent, raiz_saida=proc_dir.parent,
            config_hash="sessao_carro", dry_run=False, force=False)
        norm.write_pasta_report(rep, proc_dir.parent)
        print(f"\nNormalizado (rotação {args.rotacao} graus): {rep.processados} novos, "
              f"{rep.ja_existia} já existiam, {len(rep.pulados)} pulados -> {proc_dir}")

    # 3. CEMADEN ---------------------------------------------------------
    ped = _carregar("baixar_cemaden_ped", "estacoes/baixar_cemaden_ped.py")
    dias = dias_necessarios(v["ts_min"], v["ts_max"])
    pontos = [(m["gps"]["latitude"], m["gps"]["longitude"]) for m in metas
              if (m.get("gps") or {}).get("latitude") is not None]
    sp = [c for c in ped.ESTACOES if c not in ped.ESTACOES_COLETA_FIXA]
    codigos = estacoes_perto_da_rota(ped.ESTACOES, pontos) if pontos else sp
    faltam = pares_faltantes(codigos, dias, ped.RAW_DIR)
    print(f"\nCEMADEN: dias {', '.join(dias)}; {len(codigos)} estações perto da rota; "
          f"{len(faltam)} par(es) estação-dia fora do cache")
    if faltam and (args.dry_run or args.sem_rede):
        print("  não baixado (" + ("dry-run" if args.dry_run else "--sem-rede") +
              "): rótulos podem sair com menos estações do que o possível")
    elif faltam:
        baixar_faltantes(faltam, ped)

    # 4. rotulagem -------------------------------------------------------
    gm = _carregar("gerar_manifest", "rotulagem/gerar_manifest.py")
    cfg = yaml.safe_load(CFG_ROTULAGEM.read_text())
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        n_stage = preparar_stage(jsons, nome, args.dia, tmp / "frames")
        saida = (tmp / "manifest.csv") if args.dry_run else SAIDA_MANIFESTS / f"manifest_{nome}.csv"
        cfg["raiz_frames"] = str(tmp / "frames")
        cfg["leituras_csv"] = str(REPO / cfg["leituras_csv"])
        cfg["saida_manifest"] = str(saida)
        cfg["saida_relatorio"] = str(saida.with_suffix(".json"))
        cfg["sensibilidade_raio_km"] = []
        cfg["sensibilidade_idade_maxima_s"] = []
        cfg_path = tmp / "rotulagem.yaml"
        cfg_path.write_text(yaml.safe_dump(cfg))
        print(f"\nRotulando {n_stage} frames...")
        gm.main(["--config", str(cfg_path)])
        linhas = list(csv.DictReader(saida.open(encoding="utf-8")))
        if not args.dry_run:
            print(f"\nManifest da sessão -> {saida}")

    # 5. resumo ----------------------------------------------------------
    print("\n==== RESUMO POR CLASSE ====" + formatar_resumo(resumir_manifest(linhas)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
