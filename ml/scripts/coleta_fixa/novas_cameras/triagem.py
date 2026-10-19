#!/usr/bin/env python3
"""APOIO (antes de coletar) — aplica as regras do projeto (spec CF1) a cada câmera da sua config e diz se ela serve.

Para cada fonte de ml/configs/coleta_fixa_novas_<nome>.yaml:
  1. não pode ser câmera que a equipe já captura ou descartou (cameras_ja_capturadas.csv, coleta_fixa.yaml);
  2. não pode ficar a <= 15 km da câmera de teste (bc_atlantica): vazaria o Teste B;
  3. pluviômetro CEMADEN REPORTANDO a <= 2 km, ou >= 3 a <= 5 km (catálogo público, sem login);
  4. precisa ter posicao_verificada: true E fonte_publica preenchida (endereço real, ver GUIA.md);
  5. mostra se a live tem DVR (passado recuperável) e quanto choveu perto nos últimos 7 dias (mapa público).
Grava triagem.csv e estacoes_<nome>.json (estações a <= 5 km das câmeras aprovadas: é o que você baixa do PED).

Uso (da raiz CityRain/, venv ativo):
    python ml/scripts/coleta_fixa/novas_cameras/triagem.py --nome paulo
    python ml/scripts/coleta_fixa/novas_cameras/triagem.py --nome paulo --sem-dvr     # não consulta o YouTube
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import (CAMERA_TESTE, COLETA, RAIO_EXCLUSAO_TESTE_KM, carregar_config, catalogo,  # noqa: E402
                   chuva_horaria_publica, estacoes_perto, fontes_youtube, ja_capturadas, km, pasta, video_id)


def dvr_horas(url: str) -> str:
    sys.path.insert(0, str(COLETA))
    from recuperar_dvr import StreamDVR
    try:
        d = StreamDVR(url)
        ini = max(d.inicio, d.head_t - timedelta(hours=119))
        return f"{(d.head_t - ini).total_seconds() / 3600:.0f} h"
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "not a bot" in msg or "cookies" in msg:
            raise SystemExit("O YouTube pediu verificação de robô: pare por algumas horas e rode com --sem-dvr.")
        return "sem DVR"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nome", required=True)
    ap.add_argument("--sem-dvr", action="store_true", help="não consulta o YouTube (DVR fica em branco)")
    ap.add_argument("--sem-chuva", action="store_true", help="não consulta o mapa público de chuva")
    args = ap.parse_args()

    cfg = carregar_config(args.nome)
    cat = catalogo(args.nome)
    ids, vids = ja_capturadas()
    linhas, estacoes = [], {}
    for f in fontes_youtube(cfg):
        cid, url = f["id"], f.get("url", "")
        lat, lon = float(f["lat"]), float(f["lon"])
        motivos = []
        if cid in ids or video_id(url) in vids:
            motivos.append("JÁ CAPTURADA/DESCARTADA pela equipe")
        if km((lat, lon), CAMERA_TESTE[1:]) <= RAIO_EXCLUSAO_TESTE_KM:
            motivos.append("perto da câmera de teste (BC)")
        viz = estacoes_perto(lat, lon, cat, 5.0)
        rep2 = [(d, e) for d, e in viz if d <= 2 and e["reportando"]]
        rep5 = [(d, e) for d, e in viz if e["reportando"]]
        if not (rep2 or len(rep5) >= 3):
            motivos.append(f"pluviômetro: {len(rep2)} a ≤2 km e {len(rep5)} a ≤5 km reportando (precisa 1 ou 3)")
        if not f.get("posicao_verificada") or not f.get("fonte_publica"):
            motivos.append("posição não verificada / sem fonte_publica")
        chuva = ""
        if not args.sem_chuva and (rep2 or rep5):
            usar = [e for _, e in (rep2 or rep5)][:3]
            tot = mx = 0.0
            for e in usar:
                try:
                    h = chuva_horaria_publica(e["idestacao"])
                    tot, mx = max(tot, sum(h.values())), max(mx, max(h.values(), default=0))
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(0.5)
            chuva = f"{tot:.0f} mm / pico {mx:.1f} mm/h"
        dvr = "" if args.sem_dvr else dvr_horas(url)
        ok = not motivos
        if ok:
            for d, e in rep5:
                estacoes[e["codestacao"]] = [f"{e['nomeestacao']} ({e['cidade'].title()})", e["latitude"], e["longitude"]]
        mais_perto = f"{rep5[0][1]['nomeestacao']} {rep5[0][0]:.2f} km" if rep5 else "-"
        linhas.append({"id": cid, "aprovada": "SIM" if ok else "não", "est_2km": len(rep2), "est_5km": len(rep5),
                       "estacao_mais_perto": mais_perto, "chuva_7d": chuva, "dvr": dvr, "motivos": "; ".join(motivos)})
        print(f"{'✅' if ok else '❌'} {cid:26s} ≤2km:{len(rep2)} ≤5km:{len(rep5)} | {mais_perto:30s} | {chuva:24s} | "
              f"DVR {dvr or '-':8s} | {'; '.join(motivos)}")
    p = pasta(args.nome)
    with open(p / "triagem.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linhas[0].keys()))
        w.writeheader()
        w.writerows(linhas)
    (p / f"estacoes_{args.nome}.json").write_text(json.dumps(estacoes, ensure_ascii=False, indent=1), encoding="utf-8")
    aprov = sum(1 for l in linhas if l["aprovada"] == "SIM")
    print(f"\n{aprov} de {len(linhas)} aprovadas -> {p / 'triagem.csv'}")
    print(f"{len(estacoes)} estações para baixar do PED -> {p / f'estacoes_{args.nome}.json'}")
    print("Desative (ativa: false) na sua config as câmeras reprovadas antes de coletar.")


if __name__ == "__main__":
    main()
