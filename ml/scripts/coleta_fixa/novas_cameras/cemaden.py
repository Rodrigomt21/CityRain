#!/usr/bin/env python3
"""CEMADEN — baixa do PED/CEMADEN as leituras de 10 min das estações das SUAS câmeras (a sua conta, a sua cota).

Usa as funções do ml/scripts/estacoes/baixar_cemaden_ped.py (sem alterá-lo), mas:
  - só as estações de estacoes_<nome>.json (gerado pela triagem.py);
  - grava em ml/data/raw/novas_<nome>/estacoes/ (não mistura com o CSV da equipe);
  - pula o dia de hoje (o CEMADEN só fecha o dia no dia seguinte);
  - cada tentativa para depois de 3 respostas 401 seguidas (cota do cadastro): NÃO insista e NÃO troque de conta;
  - com --repetir, tenta de novo a cada 30 min até não faltar nada (ou 24 tentativas seguidas sem progresso).
O que já veio é pulado; 202 "Nenhum resultado" (estação sem dado no dia) também.

Credenciais: as SUAS, em ml/.env (fora do Git). Ver GUIA.md, passo 2.

Uso (da raiz CityRain/, venv ativo):
    python ml/scripts/coleta_fixa/novas_cameras/cemaden.py --nome paulo --teste        # só valida o login
    python ml/scripts/coleta_fixa/novas_cameras/cemaden.py --nome paulo --dias 6       # últimos 6 dias completos
    python ml/scripts/coleta_fixa/novas_cameras/cemaden.py --nome paulo --dias 6 --repetir
    python ml/scripts/coleta_fixa/novas_cameras/cemaden.py --nome paulo --so-previa             # só a prévia
    python ml/scripts/coleta_fixa/novas_cameras/cemaden.py --nome paulo --so-previa --previa-5km
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import REPO, estacoes_com_defeito, log, pasta  # noqa: E402

PAUSA_S = 30 * 60


class Cota(Exception):
    pass


def modulo(nome: str, exigir_lista: bool = True):
    spec = importlib.util.spec_from_file_location("ped", REPO / "ml/scripts/estacoes/baixar_cemaden_ped.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    arq = pasta(nome) / f"estacoes_{nome}.json"
    if not arq.is_file() and not exigir_lista:
        m.ESTACOES = {}
        return m
    if not arq.is_file():
        raise SystemExit(f"{arq} não existe: rode antes a triagem.py (GUIA.md, passo 4).")
    m.ESTACOES = {k: tuple(v) for k, v in json.loads(arq.read_text(encoding="utf-8")).items()}
    m.RAW_DIR = pasta(nome) / "estacoes/respostas_brutas"
    m.OUT_CSV = pasta(nome) / f"estacoes/cemaden_{nome}.csv"
    m.RAW_DIR.mkdir(parents=True, exist_ok=True)
    m.OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    if not m.OUT_CSV.is_file():  # CSV só com cabeçalho até chegar a primeira leitura
        m.OUT_CSV.write_text("fonte,estacao_id,estacao_nome,lat,lon,ts_utc,acumulado_mm,janela_min\n", encoding="utf-8")
    return m


def pendentes(m, dias: list[str]) -> int:
    n = 0
    for d in dias:
        for cod in m.ESTACOES:
            ok = (m.RAW_DIR / f"dados_pcd_{cod}_{d}.json").is_file()
            err = m.RAW_DIR / f"ERRO_{cod}_{d}.txt"
            sem = err.is_file() and "Nenhum resultado" in err.read_text(encoding="utf-8", errors="replace")
            n += 0 if (ok or sem) else 1
    return n


def tentativa(nome: str, dias: list[str]) -> tuple[int, int]:
    m = modulo(nome)
    antes = len(list(m.RAW_DIR.glob("dados_pcd_*.json")))
    if pendentes(m, dias) == 0:
        return 0, 0
    seguidos = {"n": 0}
    get_original = m._get

    def get_com_freio(url, params, token):
        status, body = get_original(url, params, token)
        seguidos["n"] = seguidos["n"] + 1 if status == 401 else 0
        if seguidos["n"] >= 3:
            raise Cota()
        return status, body

    m._get = get_com_freio
    email, senha = m.carregar_credenciais()
    try:
        m.baixar(email, senha, m.obter_token(email, senha), dias)
    except Cota:
        log(nome, "log_cemaden.txt", "  3 respostas 401 seguidas: parando esta tentativa (cota do cadastro)")
    finally:
        n = m.normalizar(sorted(m.RAW_DIR.glob("dados_pcd_*")))
        if not m.OUT_CSV.is_file():  # nenhuma estação com dado ainda: CSV só com cabeçalho
            m.OUT_CSV.write_text("fonte,estacao_id,estacao_nome,lat,lon,ts_utc,acumulado_mm,janela_min\n", encoding="utf-8")
        log(nome, "log_cemaden.txt", f"  {n} leituras -> {m.OUT_CSV}")
    return len(list(m.RAW_DIR.glob("dados_pcd_*.json"))) - antes, pendentes(m, dias)


def eventos(ts):
    ts, n, u = sorted(ts), 0, None
    for t in ts:
        if u is None or t - u > timedelta(minutes=60):
            n += 1
        u = t
    return n


def previa(nome: str, km5: bool = False) -> None:
    """Prévia dos rótulos das suas fotos com as regras do projeto (cópia da config; não mexe no oficial)."""
    p = pasta(nome)
    csv_ped = p / f"estacoes/cemaden_{nome}.csv"
    if not csv_ped.is_file():
        raise SystemExit(f"{csv_ped} não existe: baixe o CEMADEN antes (cemaden.py).")
    defeito = estacoes_com_defeito()
    limpo = p / f"estacoes/cemaden_{nome}_sem_defeito.csv"
    with open(csv_ped, encoding="utf-8") as fi, open(limpo, "w", newline="", encoding="utf-8") as fo:
        r = csv.DictReader(fi)
        w = csv.DictWriter(fo, fieldnames=r.fieldnames)
        w.writeheader()
        w.writerows(x for x in r if x["estacao_id"] not in defeito)
    base = "rotulagem_coleta_fixa_5km.yaml" if km5 else "rotulagem_coleta_fixa.yaml"
    cfg = yaml.safe_load((REPO / "ml/configs" / base).read_text(encoding="utf-8"))
    sub = p / ("previa_5km" if km5 else "previa")
    sub.mkdir(exist_ok=True)
    cfg.update(raiz_frames=f"ml/data/raw/novas_{nome}/frames",
               leituras_csv=str(limpo.relative_to(REPO)).replace("\\", "/"),
               saida_manifest=str((sub / "manifest.csv").relative_to(REPO)).replace("\\", "/"),
               saida_relatorio=str((sub / "relatorio.json").relative_to(REPO)).replace("\\", "/"))
    cfg_arq = sub / "rotulagem.yaml"
    cfg_arq.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    r = subprocess.run([sys.executable, str(REPO / "ml/scripts/rotulagem/gerar_manifest.py"), "--config", str(cfg_arq)],
                       cwd=REPO, env=dict(os.environ, PYTHONUTF8="1"), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    (sub / "saida.txt").write_text(r.stdout + r.stderr, encoding="utf-8")
    if r.returncode != 0:
        raise SystemExit(f"gerar_manifest falhou; veja {sub / 'saida.txt'}")
    tot, cl, ts, mot = Counter(), defaultdict(Counter), defaultdict(lambda: defaultdict(list)), Counter()
    for x in csv.DictReader(open(sub / "manifest.csv", encoding="utf-8")):
        tot[x["pasta"]] += 1
        if x["classe"]:
            cl[x["pasta"]][x["classe"]] += 1
            ts[x["pasta"]][x["classe"]].append(datetime.fromisoformat(x["ts_utc"].replace("Z", "")[:19]))
        else:
            mot[x["motivo_exclusao"]] += 1
    print(f"{'câmera':26s} {'fotos':>6s} {'seco':>5s} {'garoa':>6s} {'moderada (ev)':>14s} {'forte (ev)':>11s}")
    for cam in sorted(tot):
        c = cl[cam]
        print(f"{cam:26s} {tot[cam]:6d} {c['seco']:5d} {c['garoa']:6d} {c['moderada']:7d} ({eventos(ts[cam]['moderada']):2d}) "
              f"{c['forte']:5d} ({eventos(ts[cam]['forte']):2d})")
    print("\nsem rótulo, por quê:", dict(mot.most_common()))
    print(f"manifest da prévia: {sub / 'manifest.csv'}  (NÃO é o manifest oficial)")



def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nome", required=True)
    ap.add_argument("--teste", action="store_true", help="só valida o login (não baixa nada)")
    ap.add_argument("--dias", type=int, default=6, help="quantos dias completos para trás, sem contar hoje (padrão 6)")
    ap.add_argument("--de", help="ou um intervalo explícito: AAAA-MM-DD ...")
    ap.add_argument("--ate", help="... até AAAA-MM-DD (inclusive)")
    ap.add_argument("--repetir", action="store_true", help="tenta de novo a cada 30 min até completar")
    ap.add_argument("--previa", action="store_true", help="ao terminar, mostra a prévia dos rótulos (regra estrita)")
    ap.add_argument("--previa-5km", action="store_true", help="idem, com consenso a 5 km (moderada/forte)")
    ap.add_argument("--so-previa", action="store_true", help="não baixa nada: só a prévia")
    args = ap.parse_args()
    if args.so_previa:
        previa(args.nome, args.previa_5km)
        return
    m = modulo(args.nome, exigir_lista=not args.teste)
    if args.teste:
        email, senha = m.carregar_credenciais()
        m.obter_token(email, senha)
        print(f"Login ok ({email}). {len(m.ESTACOES)} estações na sua lista.")
        return
    hoje = date.today()
    if args.de:
        d0, d1 = date.fromisoformat(args.de), date.fromisoformat(args.ate or args.de)
    else:
        d0, d1 = hoje - timedelta(days=args.dias), hoje - timedelta(days=1)
    d1 = min(d1, hoje - timedelta(days=1))
    dias = [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]
    log(args.nome, "log_cemaden.txt", f"{len(m.ESTACOES)} estações x {len(dias)} dias ({dias[0]} a {dias[-1]})")
    sem_progresso = 0
    for t in range(1, 1000):
        novos, pend = tentativa(args.nome, dias)
        log(args.nome, "log_cemaden.txt", f"tentativa {t}: {novos} pares novos, {pend} pendentes")
        if pend == 0:
            log(args.nome, "log_cemaden.txt", "completo")
            break
        sem_progresso = 0 if novos else sem_progresso + 1
        if not args.repetir or sem_progresso >= 24:
            log(args.nome, "log_cemaden.txt", "parando: rode de novo mais tarde (o que já veio é pulado)")
            break
        log(args.nome, "log_cemaden.txt", f"pausa de 30 min (próxima ~{datetime.fromtimestamp(time.time() + PAUSA_S):%H:%M})")
        time.sleep(PAUSA_S)

    if args.previa or args.previa_5km:
        previa(args.nome, args.previa_5km)


if __name__ == "__main__":
    main()
