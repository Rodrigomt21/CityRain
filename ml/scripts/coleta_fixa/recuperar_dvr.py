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

Modo ``--modo-seco``: encontra trechos comprovadamente secos no CEMADEN, no critério do
rotulador (veja ``janelas_secas``): ≥ ``--min-estacoes`` (default 3) estações a
<= ``--raio-km`` com leitura em toda hora do trecho e nenhuma com chuva. Janelas de
``--duracao-min`` (default 30) centradas na leitura horária, folga de 60 min, até
``--max-janelas`` (default 10) espalhadas (>= 3 h entre si), dia e noite.
Recomendado: ``--passo-s 300`` neste modo.

O frame sai no contrato da Jetson (mesmo do ``coletor.py``) com
``capturado_em_utc`` = walltime do segmento, então ``gerar_manifest.py`` rotula
sem mudança.

Uso:
    ml/.venv/bin/python ml/scripts/coleta_fixa/recuperar_dvr.py --onde-choveu
    ml/.venv/bin/python ml/scripts/coleta_fixa/recuperar_dvr.py --modo-seco --passo-s 300
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
from collections import Counter
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


FUSO_LOCAL = timezone(timedelta(hours=-3))


def periodo_local(quando: datetime) -> str:
    """Mesma regra de gerar_manifest.py: dia = [06:00, 18:30) no horário local."""
    h = quando.astimezone(FUSO_LOCAL)
    minutos = h.hour * 60 + h.minute
    return "dia" if 6 * 60 <= minutos < 18 * 60 + 30 else "noite"


def periodo_janela(ini: datetime, fim: datetime) -> str:
    """Período (dia/noite) de uma janela, pelo seu PONTO MÉDIO (não pelo início)."""
    return periodo_local(ini + (fim - ini) / 2)


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


def _ts(texto: str) -> datetime:
    return datetime.fromisoformat(texto.replace("Z", "+00:00"))


def _hora(t: datetime) -> datetime:
    """Início da hora cheia (UTC) que contém ``t``."""
    return t.replace(minute=0, second=0, microsecond=0)


def janelas_secas(fonte, leituras: list[dict], raio_km: float, inicio: datetime, fim: datetime,
                  duracao: timedelta = timedelta(minutes=30), folga: timedelta = timedelta(minutes=60),
                  min_estacoes: int = 3, max_janelas: int = 10,
                  separacao: timedelta = timedelta(hours=3)) -> list[tuple[datetime, datetime]]:
    """Trechos comprovadamente secos, no mesmo critério de ``seco_confirmado`` do rotulador.

    Em período seco as estações do CEMADEN/PED mandam UMA leitura zerada por hora (as de
    10 min aparecem sobretudo com chuva). Por isso o julgamento é por estação, no
    intervalo ``[a - folga, b + folga]`` de cada janela candidata ``[a, b]``:

    (i)  pelo menos ``min_estacoes`` estações a <= ``raio_km`` têm >= 1 leitura em TODA hora
         cheia que toca o intervalo (hora sem leitura = buraco, e buraco nunca é seco);
    (ii) NENHUMA estação a <= ``raio_km`` (conte ou não na cobertura) tem leitura com
         acumulado_mm > 0 cuja janela de medição toque o intervalo.

    As candidatas começam na fase da leitura horária (moda do minuto das leituras menos
    ``duracao/2``; ex.: leituras em hh:00 dão janelas de hh-1:45 a hh:15), de modo que
    a leitura mais próxima fique no meio da janela e os frames possam ser rotulados.
    O período (dia/noite) vem do PONTO MÉDIO. A escolha de até ``max_janelas`` alterna
    noite e dia e, dentro de cada período, usa o ponto mais distante das já escolhidas
    (espalha ao longo do trecho), com no mínimo ``separacao`` entre inícios.

    Args:
        fonte: objeto com ``lat`` e ``lon`` da câmera.
        leituras: linhas do CSV do CEMADEN (``ts_utc`` = FIM da janela de leitura).
        raio_km: raio das estações consideradas.
        inicio, fim: limites (UTC) onde procurar.
        duracao: largura da janela de coleta.
        folga: margem seca exigida antes e depois da janela.
        min_estacoes: estações com cobertura horária completa; o padrão 3 espelha o
            consenso regional do rotulador (``min_estacoes=3``); 2 serve se a câmera
            tiver estação a <= 2 km, que vale rótulo sozinha.
        max_janelas: máximo de janelas devolvidas.
        separacao: distância mínima entre inícios de janelas escolhidas.

    Returns:
        Janelas ``(a, b)`` em UTC, ordenadas.
    """
    horas: dict[str, set[datetime]] = {}
    chuvas: list[tuple[datetime, datetime]] = []  # intervalos de medição com chuva
    minutos: list[int] = []
    for r in leituras:
        if _hav_km(fonte.lat, fonte.lon, float(r["lat"]), float(r["lon"])) > raio_km:
            continue
        t = _ts(r["ts_utc"])
        passo = timedelta(minutes=int(r.get("janela_min") or 10))
        if float(r["acumulado_mm"]) > 0:
            chuvas.append((t - passo, t))
        else:
            minutos.append(t.minute)
        horas.setdefault(r.get("estacao_id") or f"{r['lat']},{r['lon']}", set()).add(_hora(t))

    fase = (Counter(minutos).most_common(1)[0][0] if minutos else 0)
    deslocamento = timedelta(minutes=(fase - duracao.total_seconds() / 120) % 60)

    candidatas = []
    a = _hora(inicio) + deslocamento
    if a < inicio:
        a += timedelta(hours=1)
    while a + duracao <= fim:
        b = a + duracao
        lo, hi = a - folga, b + folga
        if not any(x < hi and y > lo for x, y in chuvas):
            necessarias = {_hora(lo) + timedelta(hours=k) for k in range(int((hi - _hora(lo)) / timedelta(hours=1)) + 1)
                           if _hora(lo) + timedelta(hours=k) < hi}
            if sum(1 for h in horas.values() if necessarias <= h) >= min_estacoes:
                candidatas.append((a, b))
        a += timedelta(hours=1)

    filas = {p: [c for c in candidatas if periodo_janela(*c) == p] for p in ("noite", "dia")}
    escolhidas: list[tuple[datetime, datetime]] = []
    vez = 0
    while len(escolhidas) < max_janelas and any(filas.values()):
        p = ("noite", "dia")[vez % 2]
        vez += 1
        filas[p] = [c for c in filas[p] if all(abs(c[0] - e[0]) >= separacao for e in escolhidas)]
        if not filas[p]:
            continue
        if escolhidas:  # ponto mais distante das já escolhidas (empate: o mais cedo)
            melhor = max(filas[p], key=lambda c: (min(abs(c[0] - e[0]) for e in escolhidas), -c[0].timestamp()))
        else:
            melhor = filas[p][len(filas[p]) // 2]
        escolhidas.append(melhor)
        filas[p].remove(melhor)
    return sorted(escolhidas)


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
    ap.add_argument("--modo-seco", action="store_true")
    ap.add_argument("--fonte", help="id da fonte (modo manual)")
    ap.add_argument("--de", help="ISO 8601 com fuso (modo manual)")
    ap.add_argument("--ate", help="ISO 8601 com fuso (modo manual)")
    ap.add_argument("--passo-s", type=float, default=60.0)
    ap.add_argument("--raio-km", type=float, default=5.0)
    ap.add_argument("--margem-min", type=float, default=30.0)
    ap.add_argument("--max-janelas", type=int, default=10)
    ap.add_argument("--min-estacoes", type=int, default=3, help="estações com cobertura horária completa (modo seco)")
    ap.add_argument("--duracao-min", type=float, default=30.0)
    ap.add_argument("--estacoes", type=Path, default=RAIZ / "ml/data/raw/estacoes/normalizado/cemaden_ped.csv")
    ap.add_argument("--desde", help="ISO 8601: ignora o que vem antes (evita re-baixar colheitas anteriores)")
    args = ap.parse_args()

    cfg = yaml.safe_load(args.config.read_text())
    destino = RAIZ / cfg.get("destino", "ml/data/raw/coleta_fixa")
    fontes = [f for f in carregar_fontes(cfg) if f.tipo == "youtube"]
    if args.fonte:
        fontes = [f for f in fontes if f.id == args.fonte]

    leituras = []
    if args.onde_choveu or args.modo_seco:
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
        if args.modo_seco:
            janelas = janelas_secas(f, leituras, args.raio_km, inicio_dvr, dvr.head_t,
                                    duracao=timedelta(minutes=args.duracao_min), min_estacoes=args.min_estacoes,
                                    max_janelas=args.max_janelas)
        elif args.onde_choveu:
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
