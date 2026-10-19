#!/usr/bin/env python3
"""APOIO (antes de coletar) — procura lives do YouTube que estejam AO VIVO, por termos de busca e/ou canais.

Sai uma planilha (lives_encontradas.csv) com título, canal, link e os trechos da descrição que parecem
endereço ou link de mapa, para você ler e escolher candidatas. Já pula as câmeras que a equipe captura
ou descartou (cameras_ja_capturadas.csv + ml/configs/coleta_fixa.yaml).

Ritmo: UMA consulta por vez, com pausa (padrão 3 s). Não aumente o ritmo: rajada de pedidos faz o YouTube
pedir "confirme que não é um robô" e derruba também o coletor ao vivo de quem está na mesma rede.

Exemplos (da raiz CityRain/, venv ativo):
    python ml/scripts/coleta_fixa/novas_cameras/buscar_lives.py --nome paulo --cidade "Joinville" --cidade "Blumenau"
    python ml/scripts/coleta_fixa/novas_cameras/buscar_lives.py --nome paulo --termo "câmera ao vivo serra"
    python ml/scripts/coleta_fixa/novas_cameras/buscar_lives.py --nome paulo --canal https://www.youtube.com/@ubacam
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import ja_capturadas, pasta, video_id  # noqa: E402

FILTRO_LIVE = "EgJAAQ%3D%3D"  # filtro "Ao vivo" da busca do YouTube
NAO_E_CAMERA = re.compile(r"(?i)\b(jogo|game|gameplay|futebol|not[ií]cias|jornal|news|r[aá]dio|m[uú]sica|culto|missa|"
                          r"igreja ao vivo|podcast|aula|minecraft|gta|lofi|lo-fi|ora[cç][aã]o|louvor|bingo|trading|"
                          r"cassino|fazenda \d+|estude comigo|study with me|asmr|relax|sleep|irl|driving tour)\b")
ENDERECO = re.compile(r"(?i)(\b(rua|av\.?|avenida|alameda|pra[cç]a|estrada|rodovia|esquina|cep|n[º°o]\s*\d|edif[ií]cio|"
                      r"condom[ií]nio|bairro|localiza|endere[cç]o|instalad[ao]|📍)|maps\.app|goo\.gl/maps|google\.com/maps)")


def ytdlp() -> str:
    exe = shutil.which("yt-dlp")
    if not exe:
        raise SystemExit("yt-dlp não encontrado no PATH: ative o venv (GUIA.md, passo 1).")
    return exe


def listar(url: str, limite: int) -> list[dict]:
    r = subprocess.run([ytdlp(), "--flat-playlist", "-J", "--playlist-end", str(limite), "--no-warnings", url],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    if r.returncode != 0:
        print(f"  [aviso] falhou: {r.stderr.strip()[-160:]}")
        return []
    return [e for e in json.loads(r.stdout).get("entries") or [] if e.get("id")]


def detalhes(vid: str) -> dict | None:
    r = subprocess.run([ytdlp(), "-J", "--skip-download", "--no-warnings", f"https://www.youtube.com/watch?v={vid}"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    if r.returncode != 0:
        if "not a bot" in r.stderr or "cookies" in r.stderr:
            raise SystemExit("\nO YouTube pediu verificação de robô: PARE por algumas horas (não use cookies nem VPN).")
        return None
    return json.loads(r.stdout)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nome", required=True, help="seu nome (define a pasta de dados)")
    ap.add_argument("--cidade", action="append", default=[], help='busca "<cidade> ao vivo câmera" (repetível)')
    ap.add_argument("--termo", action="append", default=[], help="termo livre de busca (repetível)")
    ap.add_argument("--canal", action="append", default=[], help="URL do canal: lista as lives ao vivo dele (repetível)")
    ap.add_argument("--por-busca", type=int, default=30, help="resultados lidos por busca (padrão 30)")
    ap.add_argument("--max-detalhes", type=int, default=60, help="no máximo quantas descrições baixar (padrão 60)")
    ap.add_argument("--pausa-s", type=float, default=3.0)
    args = ap.parse_args()
    if not (args.cidade or args.termo or args.canal):
        ap.error("informe ao menos um --cidade, --termo ou --canal")

    ids, vids = ja_capturadas()
    termos = [f"{c} ao vivo câmera" for c in args.cidade] + args.termo
    achados: dict[str, dict] = {}
    for t in termos:
        url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(t)}&sp={FILTRO_LIVE}"
        res = listar(url, args.por_busca)
        print(f"busca {t!r}: {len(res)}")
        for e in res:
            achados.setdefault(e["id"], {"titulo": e.get("title") or "", "canal": e.get("channel") or e.get("uploader") or "", "origem": t})
        time.sleep(args.pausa_s)
    for c in args.canal:
        res = [e for e in listar(c.rstrip("/") + "/streams", 100) if e.get("live_status") == "is_live"]
        print(f"canal {c}: {len(res)} ao vivo")
        for e in res:
            achados.setdefault(e["id"], {"titulo": e.get("title") or "", "canal": e.get("channel") or "", "origem": c})
        time.sleep(args.pausa_s)

    novos = {v: a for v, a in achados.items() if v not in vids and not NAO_E_CAMERA.search(a["titulo"] + " " + a["canal"])}
    print(f"\n{len(achados)} lives achadas; {len(achados) - len(novos)} descartadas (já capturadas/descartadas pela equipe "
          f"ou não parecem câmera); baixando descrição de até {args.max_detalhes}...")
    linhas = []
    for i, (vid, a) in enumerate(list(novos.items())[: args.max_detalhes], 1):
        j = detalhes(vid)
        time.sleep(args.pausa_s)
        if not j or j.get("live_status") != "is_live":
            continue
        desc = j.get("description") or ""
        trechos = [s.strip() for s in re.split(r"\n|(?<=[.!?])\s", desc) if ENDERECO.search(s) and len(s) < 300]
        linhas.append({"video": vid, "url": f"https://www.youtube.com/watch?v={vid}", "canal": j.get("channel"),
                       "canal_url": j.get("channel_url"), "titulo": j.get("title"),
                       "resolucao": f"{j.get('width')}x{j.get('height')}",
                       "pistas_de_endereco": " | ".join(dict.fromkeys(trechos))[:600],
                       "proibe_uso": "SIM" if re.search(r"(?i)proibid|n[aã]o autorizad|sem autoriza", desc) else "",
                       "origem_busca": a["origem"]})
        print(f"  {i:3d}. {vid} | {j.get('channel')} | {j.get('title')[:70]}")
    saida = pasta(args.nome) / "lives_encontradas.csv"
    novo = not saida.exists()
    with open(saida, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()) if linhas else ["video"])
        if novo:
            w.writeheader()
        w.writerows(linhas)
    print(f"\n{len(linhas)} lives ao vivo com descrição -> {saida}")
    print("Próximo: ler as descrições, achar o ENDEREÇO de cada câmera e montar a sua config (GUIA.md, passo 3).")


if __name__ == "__main__":
    main()
