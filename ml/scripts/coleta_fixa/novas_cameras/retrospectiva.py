#!/usr/bin/env python3
"""RETROSPECTIVA — baixa o PASSADO das suas câmeras pelo DVR do YouTube (o "voltar no tempo" da live, ~5 dias).

Faz tudo sozinho, em ciclos:
  1. PLANEJA: acha os buracos (> 30 min sem foto sua) dentro do que o DVR ainda alcança e marca as horas de chuva
     (pelas suas leituras do PED, se já baixou; senão pelo mapa público). Só câmeras aprovadas na triagem.
  2. BAIXA devagar: um trecho por vez, por até 30 min (padrão 1 foto a cada 10 min: sem fotos repetidas).
  3. PAUSA 30 min e volta ao 1 (replanejando: o que já baixou não é pedido de novo). Termina quando não sobra nada.
PARA DE VEZ na primeira resposta "confirme que não é um robô" do YouTube. Não use cookies, VPN nem outra rede
para contornar: espere algumas horas e rode de novo (continua de onde parou).

Uso (da raiz CityRain/, venv ativo):
    python ml/scripts/coleta_fixa/novas_cameras/retrospectiva.py --nome paulo
    python ml/scripts/coleta_fixa/novas_cameras/retrospectiva.py --nome paulo --so-planejar   # só mostra o plano
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import (COLETA, REPO, carregar_config, catalogo, chuva_horaria_publica,  # noqa: E402
                   config_path, estacoes_com_defeito, estacoes_perto, fontes_youtube, log, pasta)

BLOQUEIO = ("not a bot", "cookies")
L = "log_retrospectiva.txt"


def unir(iv):
    out = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def cortar(a, b, cortes):
    out, t = [], a
    for c0, c1 in cortes:
        if c1 <= t or c0 >= b:
            continue
        if c0 > t:
            out.append((t, c0, False))
        out.append((max(c0, t), min(c1, b), True))
        t = min(c1, b)
    if t < b:
        out.append((t, b, False))
    return out


def planejar(nome: str, passo_chuva: int, passo_resto: int, horas: float, desistidos: set) -> list[tuple]:
    """Lista de (camera, inicio, fim, passo), ordenada pelo horário (o mais antigo some primeiro do DVR)."""
    cfg = carregar_config(nome)
    p = pasta(nome)
    tri = p / "triagem.csv"
    if not tri.is_file():
        raise SystemExit("Rode antes a triagem.py: só câmeras aprovadas entram na retrospectiva.")
    aprovadas = {r["id"] for r in csv.DictReader(open(tri, encoding="utf-8")) if r["aprovada"] == "SIM"}
    agora = datetime.now(timezone.utc)
    inicio = agora - timedelta(hours=horas)
    defeito = estacoes_com_defeito()
    cat = catalogo(nome)
    ped = defaultdict(list)
    csv_ped = p / f"estacoes/cemaden_{nome}.csv"
    if csv_ped.is_file():
        for r in csv.DictReader(open(csv_ped, encoding="utf-8")):
            if r["estacao_id"] not in defeito and float(r["acumulado_mm"] or 0) > 0:
                ped[r["estacao_id"]].append(datetime.fromisoformat(r["ts_utc"].replace("Z", "+00:00")))
    ts = defaultdict(list)
    for j in (p / "frames").glob("*/frame_*.json"):
        m = json.loads(j.read_text(encoding="utf-8"))
        ts[j.parent.name].append(datetime.fromisoformat(m["capturado_em_utc"].replace("Z", "+00:00")))
    plano = []
    log(nome, L, f"planejando: DVR desde ~{inicio:%d/%m %H:%M} UTC | chuva pelo {'PED' if ped else 'mapa público'}")
    for f in fontes_youtube(cfg):
        cid = f["id"]
        if cid not in aprovadas:
            continue
        viz = [(d, e) for d, e in estacoes_perto(float(f["lat"]), float(f["lon"]), cat, 5) if e["reportando"]]
        a2 = [e for d, e in viz if d <= 2]
        marcas = defaultdict(int)
        for e in (a2 or [e for _, e in viz]):
            if ped:
                horas_chuva = [(t, 10) for t in ped.get(e["codestacao"], [])]
            else:
                try:
                    horas_chuva = [(t, 60) for t, v in chuva_horaria_publica(e["idestacao"]).items() if v > 0]
                except Exception:  # noqa: BLE001
                    horas_chuva = []
                time.sleep(0.5)
            for t, dur in horas_chuva:
                marcas[(t, dur)] += 1
        minimo = 1 if a2 else 2
        margem = timedelta(minutes=40 if ped else 150)  # mapa público: convenção de hora incerta (fontes-estacoes.md)
        chuva = unir([(t - timedelta(minutes=dur) - margem, t + margem) for (t, dur), n in marcas.items() if n >= minimo])
        v = sorted(x for x in ts[cid] if x >= inicio)
        marcos = [inicio] + v + [agora - timedelta(minutes=5)]
        buracos = [(a + timedelta(minutes=2), b - timedelta(minutes=2)) for a, b in zip(marcos, marcos[1:])
                   if b - a > timedelta(minutes=30)]
        n_ch = n_re = 0
        for a, b in buracos:
            for ini, fim, eh in cortar(a, b, chuva):
                if fim - ini < timedelta(minutes=5) or (cid, ini.replace(second=0, microsecond=0).isoformat()) in desistidos:
                    continue
                passo = passo_chuva if eh else passo_resto
                plano.append((cid, ini, fim, passo))
                n = (fim - ini).total_seconds() / passo
                n_ch, n_re = (n_ch + n, n_re) if eh else (n_ch, n_re + n)
        log(nome, L, f"  {cid:26s} buracos {len(buracos):3d} | fotos em chuva ≈ {int(n_ch):5d} | resto ≈ {int(n_re):5d}")
    return sorted(plano, key=lambda x: x[1])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nome", required=True)
    ap.add_argument("--passo-chuva", type=int, default=600, help="segundos entre fotos nas horas de chuva (padrão 600)")
    ap.add_argument("--passo-resto", type=int, default=600, help="segundos entre fotos no resto (padrão 600)")
    ap.add_argument("--horas", type=float, default=117, help="até quantas horas para trás (o DVR guarda ~119 h)")
    ap.add_argument("--bloco-min", type=float, default=30)
    ap.add_argument("--pausa-min", type=float, default=30)
    ap.add_argument("--so-planejar", action="store_true")
    args = ap.parse_args()
    p = pasta(args.nome)
    arq_desist = p / "retrospectiva_desistidos.json"   # trechos sem DVR ou com 3 falhas: não tentar de novo
    desistidos = set(map(tuple, json.loads(arq_desist.read_text(encoding="utf-8")))) if arq_desist.is_file() else set()
    falhas: dict[str, int] = {}
    env = dict(os.environ, PYTHONUTF8="1")
    cfg = str(config_path(args.nome))

    def desistir(cam, ini):
        desistidos.add((cam, ini.replace(second=0, microsecond=0).isoformat()))
        arq_desist.write_text(json.dumps(sorted(desistidos)), encoding="utf-8")

    ciclo = 0
    while True:
        ciclo += 1
        plano = planejar(args.nome, args.passo_chuva, args.passo_resto, args.horas, desistidos)
        if args.so_planejar:
            log(args.nome, L, f"{len(plano)} trechos no plano (só planejamento, nada baixado)")
            return
        if not plano:
            log(args.nome, L, "FIM: não sobrou buraco dentro do DVR")
            return
        log(args.nome, L, f"ciclo {ciclo}: {len(plano)} trechos; baixando por até {args.bloco_min:.0f} min")
        t0 = time.time()
        for cam, ini, fim, passo in plano:
            if (time.time() - t0) / 60 > args.bloco_min:
                break
            r = subprocess.run([sys.executable, "-u", str(COLETA / "recuperar_dvr.py"), "--config", cfg, "--fonte", cam,
                                "--de", ini.isoformat(), "--ate", fim.isoformat(), "--passo-s", str(passo)],
                               cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
            saida = (r.stdout or "") + (r.stderr or "")
            with open(p / "log_retrospectiva_detalhe.txt", "a", encoding="utf-8") as fh:
                fh.write(f"\n=== {cam} {ini:%d/%m %H:%M}->{fim:%d/%m %H:%M}Z passo {passo}s\n{saida}")
            resumo = " | ".join(l.strip() for l in saida.splitlines() if "frames" in l or "FALHA" in l or "sem DVR" in l)
            log(args.nome, L, f"  {cam} {ini:%d/%m %H:%M}->{fim:%d/%m %H:%M}Z: {resumo[-140:]}")
            if any(x in saida for x in BLOQUEIO):
                log(args.nome, L, "YouTube pediu verificação de robô: PARANDO. Espere algumas horas e rode de novo.")
                return
            k = f"{cam}|{ini:%Y%m%d%H%M}"
            if "sem DVR" in saida:
                log(args.nome, L, f"  {cam}: sem DVR (live sem passado ou reiniciou): trecho abandonado")
                desistir(cam, ini)
            elif "FALHA" in saida or " 0 frames" in saida:
                falhas[k] = falhas.get(k, 0) + 1
                if falhas[k] >= 3:
                    log(args.nome, L, f"  {cam}: 3 tentativas sem foto neste trecho (câmera congelada?): abandonado")
                    desistir(cam, ini)
            time.sleep(45)
        log(args.nome, L, f"pausa de {args.pausa_min:.0f} min (próximo ciclo ~{datetime.fromtimestamp(time.time() + args.pausa_min * 60):%H:%M})")
        time.sleep(args.pausa_min * 60)


if __name__ == "__main__":
    main()
