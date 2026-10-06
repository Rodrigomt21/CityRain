#!/usr/bin/env python3
"""Recupera frames do PASSADO das lives do YouTube (DVR de 120 h) onde choveu.

As lives de ``ml/configs/coleta_fixa.yaml`` guardam as últimas ~120 h. O DASH
delas é uma sequência de segmentos de 5 s numerados (``&sq=N``), e cada
segmento traz o próprio instante de ingestão (``Ingestion-Walltime-Us``). Então
dá para pedir exatamente o minuto que interessa, sem baixar o vídeo inteiro.

Modo ``--onde-choveu`` (o normal): lê a série de 10 min do CEMADEN
(``ml/data/raw/estacoes/normalizado/cemaden_ped.csv``), acha os intervalos em que
algum pluviômetro a <= ``--raio-km`` da câmera registrou chuva, abre
``--margem-min`` antes e depois (inclui o começo/fim seco do evento) e baixa 1
frame a cada ``--passo-s``. Rodar antes ``baixar_cemaden_ped.py --dias ...``.

O frame sai no contrato da Jetson (mesmo do ``coletor.py``) com
``capturado_em_utc`` = walltime do segmento, então ``gerar_manifest.py`` rotula
sem mudança.

Uso:
    ml/.venv/bin/python ml/scripts/coleta_fixa/recuperar_dvr.py --onde-choveu
    ml/.venv/bin/python ml/scripts/coleta_fixa/recuperar_dvr.py --fonte ubatuba_tenorio \
        --de 2026-10-04T18:00-03:00 --ate 2026-10-04T20:00-03:00
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from coletor import carregar_fontes, gravar_frame  # noqa: E402

SEG_S_PADRAO = 5.0  # chute inicial; a duração real varia por live (5 s em Ubatuba, 2 s no Centro) e é calibrada
_WALL = re.compile(rb"Ingestion-Walltime-Us: (\d+)")
_SEQ = re.compile(rb"Sequence-Number: (\d+)")


class StreamDVR:
    """Acesso por instante aos segmentos de uma live do YouTube."""

    def __init__(self, url_video: str, altura: int = 480) -> None:
        self.url_video, self.altura = url_video, altura
        self.renovar()

    def renovar(self) -> None:
        """Resolve a URL assinada do formato (expira em algumas horas) e recalibra."""
        url_video, altura = self.url_video, self.altura
        r = subprocess.run(["yt-dlp", "--live-from-start", "-J", url_video], capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"yt-dlp: {r.stderr.strip()[-200:]}")
        info = json.loads(r.stdout)
        self.inicio = datetime.fromtimestamp(info.get("release_timestamp") or 0, timezone.utc)
        fmts = [f for f in info["formats"]
                if f.get("protocol", "").startswith("http_dash") and f.get("vcodec") not in (None, "none")]
        if not fmts:
            raise RuntimeError("live sem DASH (sem DVR)")
        f = min(fmts, key=lambda f: abs((f.get("height") or 0) - altura))
        self.url, self.headers = f["url"], f.get("http_headers", {})
        self.head_sq, self.head_t = self._ler(None)
        # duração real do segmento: walltime de um segmento ~1 h antes do topo
        ref_sq, ref_t = self._ler(self.head_sq - round(3600 / SEG_S_PADRAO))
        self.seg_s = (self.head_t - ref_t).total_seconds() / (self.head_sq - ref_sq)

    def _ler(self, sq: int | None) -> tuple[int, datetime]:
        b = self.segmento(sq)
        s, w = _SEQ.search(b), _WALL.search(b)
        if not (s and w):
            raise RuntimeError("segmento sem Sequence-Number/Walltime")
        return int(s.group(1)), datetime.fromtimestamp(int(w.group(1)) / 1e6, timezone.utc)

    def segmento(self, sq: int | None) -> bytes:
        url = self.url + (f"&sq={sq}" if sq is not None else "")
        return urllib.request.urlopen(urllib.request.Request(url, headers=self.headers), timeout=30).read()

    def sq_para(self, quando: datetime) -> int:
        """Número do segmento que contém ``quando`` (estimativa linear + 1 correção)."""
        sq = self.head_sq - round((self.head_t - quando).total_seconds() / self.seg_s)
        for _ in range(2):  # duas correções: a taxa não é perfeitamente constante
            real_sq, real_t = self._ler(sq)
            sq = real_sq + round((quando - real_t).total_seconds() / self.seg_s)
        return sq

    def frame(self, sq: int) -> tuple[bytes, datetime]:
        """JPEG do 1º quadro do segmento e o instante de ingestão dele."""
        b = self.segmento(sq)
        w = _WALL.search(b)
        quando = datetime.fromtimestamp(int(w.group(1)) / 1e6, timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "s.mp4").write_bytes(b)
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", f"{tmp}/s.mp4", "-frames:v", "1",
                            "-q:v", "2", f"{tmp}/f.jpg"], check=True, timeout=60)
            return Path(tmp, "f.jpg").read_bytes(), quando


def _hav_km(a: float, b: float, c: float, d: float) -> float:
    p = math.pi / 180
    h = math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def janelas_com_chuva(fonte, leituras: list[dict], raio_km: float, margem: timedelta,
                      inicio_dvr: datetime) -> list[tuple[datetime, datetime]]:
    """Intervalos (UTC) com chuva em algum pluviômetro perto, com margem, unidos e cortados ao DVR."""
    blocos = []
    for r in leituras:
        if float(r["acumulado_mm"]) <= 0:
            continue
        if _hav_km(fonte.lat, fonte.lon, float(r["lat"]), float(r["lon"])) > raio_km:
            continue
        fim = datetime.fromisoformat(r["ts_utc"].replace("Z", "+00:00"))
        ini = fim - timedelta(minutes=int(r.get("janela_min") or 10))
        blocos.append((max(ini - margem, inicio_dvr), fim + margem))
    blocos.sort()
    unidos: list[tuple[datetime, datetime]] = []
    for a, b in blocos:
        if b <= inicio_dvr:
            continue
        if unidos and a <= unidos[-1][1]:
            unidos[-1] = (unidos[-1][0], max(unidos[-1][1], b))
        else:
            unidos.append((a, b))
    return unidos


def recuperar(fonte, dvr: StreamDVR, de: datetime, ate: datetime, passo_s: float, destino: Path) -> int:
    agora = datetime.now(timezone.utc)
    ate = min(ate, agora - timedelta(seconds=30))
    if ate <= de:
        return 0
    sq0, sq1 = dvr.sq_para(de), dvr.sq_para(ate)
    passo = max(1, round(passo_s / dvr.seg_s))
    n = 0
    for sq in range(sq0, sq1 + 1, passo):
        try:
            jpg, quando = dvr.frame(sq)
        except urllib.error.HTTPError as e:
            if e.code in (400, 403):  # URL assinada expirou: renova e tenta de novo
                dvr.renovar()
                try:
                    jpg, quando = dvr.frame(sq)
                except Exception as e2:  # noqa: BLE001
                    print(f"  sq {sq}: {e2}", flush=True)
                    continue
            else:
                print(f"  sq {sq}: {e}", flush=True)
                continue
        except (subprocess.CalledProcessError, RuntimeError) as e:
            print(f"  sq {sq}: {e}", flush=True)
            continue
        if not (de - timedelta(minutes=2) <= quando <= ate + timedelta(minutes=2)):
            continue  # fora da janela pedida (ex.: antes do início da live)
        fonte.tipo = "youtube_dvr"
        if gravar_frame(jpg, fonte, destino, quando):
            n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=RAIZ / "ml/configs/coleta_fixa.yaml")
    ap.add_argument("--onde-choveu", action="store_true")
    ap.add_argument("--fonte", help="id da fonte (modo manual)")
    ap.add_argument("--de", help="ISO 8601 com fuso (modo manual)")
    ap.add_argument("--ate", help="ISO 8601 com fuso (modo manual)")
    ap.add_argument("--passo-s", type=float, default=60.0)
    ap.add_argument("--raio-km", type=float, default=5.0)
    ap.add_argument("--margem-min", type=float, default=30.0)
    ap.add_argument("--estacoes", type=Path, default=RAIZ / "ml/data/raw/estacoes/normalizado/cemaden_ped.csv")
    ap.add_argument("--desde", help="ISO 8601: ignora o que vem antes (evita re-baixar colheitas anteriores)")
    args = ap.parse_args()

    cfg = yaml.safe_load(args.config.read_text())
    destino = RAIZ / cfg.get("destino", "ml/data/raw/coleta_fixa")
    fontes = [f for f in carregar_fontes(cfg) if f.tipo == "youtube"]
    if args.fonte:
        fontes = [f for f in fontes if f.id == args.fonte]

    leituras = []
    if args.onde_choveu:
        import csv

        with open(args.estacoes, newline="") as fh:
            leituras = list(csv.DictReader(fh))

    for f in fontes:
        try:
            dvr = StreamDVR(f.url)
        except Exception as e:  # noqa: BLE001
            print(f"[{f.id}] sem DVR: {e}", flush=True)
            continue
        # o DVR guarda ~120 h, mas nunca antes do início da própria live
        inicio_dvr = max(dvr.head_t - timedelta(hours=119), dvr.inicio)
        if args.desde:
            inicio_dvr = max(inicio_dvr, datetime.fromisoformat(args.desde).astimezone(timezone.utc))
        if args.onde_choveu:
            janelas = janelas_com_chuva(f, leituras, args.raio_km, timedelta(minutes=args.margem_min), inicio_dvr)
        else:
            janelas = [(datetime.fromisoformat(args.de).astimezone(timezone.utc),
                        datetime.fromisoformat(args.ate).astimezone(timezone.utc))]
        total_min = sum((b - a).total_seconds() for a, b in janelas) / 60
        print(f"[{f.id}] {len(janelas)} janela(s), {total_min:.0f} min, segmento de {dvr.seg_s:.2f} s", flush=True)
        for a, b in janelas:
            try:
                n = recuperar(f, dvr, a, b, args.passo_s, destino)
            except Exception as e:  # noqa: BLE001 — uma janela ruim não derruba as outras
                print(f"  {a:%d/%m %H:%M}–{b:%H:%M}Z: FALHA {e}", flush=True)
                continue
            print(f"  {a:%d/%m %H:%M}–{b:%H:%M}Z: {n} frames", flush=True)


if __name__ == "__main__":
    main()
