"""Funções compartilhadas pelo kit de novas câmeras (ver GUIA.md).

Caminhos por pessoa (``--nome paulo`` / ``--nome moreno``):
  - config das câmeras:  ml/configs/coleta_fixa_novas_<nome>.yaml   (versionável: não tem segredo)
  - dados (fora do Git): ml/data/raw/novas_<nome>/                   (frames, estações, planos, logs)
"""
from __future__ import annotations

import csv
import json
import math
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

AQUI = Path(__file__).resolve().parent
REPO = AQUI.parents[3]                      # novas_cameras -> coleta_fixa -> scripts -> ml -> CityRain
COLETA = REPO / "ml/scripts/coleta_fixa"
UA = {"User-Agent": "CityRain-TCC-IMT/1.0 (pesquisa academica; triagem de cameras publicas)"}
CATALOGO_URL = "https://resources.cemaden.gov.br/dados/311_24.json"
HORARIO_URL = "https://mapservices.cemaden.gov.br/MapaInterativoWS/resources/horario/{id}/{horas}"
CAMERA_TESTE = ("bc_atlantica", -26.9930, -48.6330)   # Teste B: nenhuma câmera nova a <= 15 km dela
RAIO_EXCLUSAO_TESTE_KM = 15.0


def pasta(nome: str) -> Path:
    p = REPO / "ml/data/raw" / f"novas_{nome}"
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_path(nome: str) -> Path:
    return REPO / "ml/configs" / f"coleta_fixa_novas_{nome}.yaml"


def carregar_config(nome: str) -> dict:
    p = config_path(nome)
    if not p.is_file():
        raise SystemExit(f"Config não encontrada: {p}\nCopie exemplo_minhas_cameras.yaml para esse caminho (GUIA.md, passo 3).")
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def fontes_youtube(cfg: dict) -> list[dict]:
    return [f for f in cfg.get("fontes", []) if f.get("ativa", True) and f.get("tipo") == "youtube"]


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distância haversine em km entre (lat, lon) a e b."""
    p = math.pi / 180
    h = (math.sin((b[0] - a[0]) * p / 2) ** 2
         + math.cos(a[0] * p) * math.cos(b[0] * p) * math.sin((b[1] - a[1]) * p / 2) ** 2)
    return 12742.0 * math.asin(math.sqrt(h))


def video_id(url: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|/live/)([\w-]{11})", url or "")
    return m.group(1) if m else (url or "").rstrip("/")


def estacoes_com_defeito() -> set[str]:
    arq = AQUI / "estacoes_com_defeito.txt"
    return {l.split()[0] for l in arq.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")}


def catalogo(nome: str, atualizar: bool = False) -> list[dict]:
    """Pluviômetros CEMADEN do catálogo público (sem login). 'reportando' = tem acumulado nas últimas 24 h."""
    cache = pasta(nome) / "catalogo_311_24.json"
    if atualizar or not cache.is_file() or (datetime.now().timestamp() - cache.stat().st_mtime) > 86400:
        txt = urllib.request.urlopen(urllib.request.Request(CATALOGO_URL, headers=UA), timeout=60).read().decode("utf-8")
        dados = json.loads(txt[txt.index("(") + 1: txt.rindex(")")])
        cache.write_text(json.dumps(dados[0]["estacao"], ensure_ascii=False), encoding="utf-8")
    defeito = estacoes_com_defeito()
    est = json.loads(cache.read_text(encoding="utf-8"))
    return [dict(e, reportando=e.get("acumulado") is not None and e["codestacao"] not in defeito)
            for e in est if e.get("tipoestacao") == "Pluviométrica"]


def estacoes_perto(lat: float, lon: float, cat: list[dict], raio: float = 5.0) -> list[tuple[float, dict]]:
    viz = sorted(((km((lat, lon), (e["latitude"], e["longitude"])), e) for e in cat), key=lambda t: t[0])
    return [(d, e) for d, e in viz if d <= raio]


def chuva_horaria_publica(idestacao: int, horas: int = 168) -> dict[datetime, float]:
    """mm por hora (UTC) do Mapa Interativo público. Só para TRIAGEM (o rótulo vem do PED, de 10 em 10 min)."""
    url = HORARIO_URL.format(id=idestacao, horas=horas)
    j = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read().decode("utf-8"))
    out = {}
    for dia, vals in zip(j.get("datas") or [], j.get("acumulados") or []):
        d = datetime.strptime(dia, "%d/%m/%Y").replace(tzinfo=timezone.utc)
        for rot, v in zip(j["horarios"], vals):
            if v is not None:
                out[d + timedelta(hours=int(rot.rstrip("h")))] = float(v)
    return out


def ja_capturadas() -> tuple[set[str], set[str]]:
    """(ids, video_ids) de câmeras que a equipe já captura ou já descartou: não procurar de novo."""
    ids, vids = set(), set()
    arq = AQUI / "cameras_ja_capturadas.csv"
    if arq.is_file():
        for r in csv.DictReader(open(arq, encoding="utf-8")):
            if r["situacao"].startswith("PISTA"):
                continue  # pista = candidata livre para quem quiser assumir
            ids.add(r["id"])
            vids.add(video_id(r["url"]))
    for f in yaml.safe_load((REPO / "ml/configs/coleta_fixa.yaml").read_text(encoding="utf-8")).get("fontes", []):
        ids.add(f["id"])
        vids.add(video_id(f.get("url", "")))
    return ids, vids


def log(nome: str, arquivo: str, msg: str) -> None:
    linha = f"[{datetime.now():%d/%m %H:%M}] {msg}"
    print(linha, flush=True)
    with open(pasta(nome) / arquivo, "a", encoding="utf-8") as f:
        f.write(linha + "\n")
