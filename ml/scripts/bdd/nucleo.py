"""Funções puras do pipeline BDD100K x MRMS (testadas em tests/test_bdd_mrms.py)."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone

LIMIAR_GAROA = 2.5
LIMIAR_MODERADA = 10.0
CLASSES = ("seco", "garoa", "moderada", "forte")
FRAME_MS = 10_000  # o frame rotulado do BDD100K é o do 10o segundo


def classe_de(mmh: float) -> str:
    """seco (0) / garoa (<=2.5) / moderada (2.5,10] / forte (>10)."""
    if mmh <= 0:
        return "seco"
    if mmh <= LIMIAR_GAROA:
        return "garoa"
    if mmh <= LIMIAR_MODERADA:
        return "moderada"
    return "forte"


def mrms_valido(v: float | None) -> float | None:
    """MRMS usa -3 (sem cobertura) e -1/-999 (sem dado): vira None."""
    if v is None or v != v or v < 0:
        return None
    return float(v)


def timestamp_mrms_mais_proximo(utc: datetime) -> datetime:
    """Arredonda para o múltiplo de 2 min mais próximo (UTC, sem segundos)."""
    utc = utc.astimezone(timezone.utc) if utc.tzinfo else utc.replace(tzinfo=timezone.utc)
    base = utc.replace(second=0, microsecond=0)
    segundos = (utc - base).total_seconds() + (base.minute % 2) * 60
    base = base - timedelta(minutes=base.minute % 2)
    return base + timedelta(minutes=2) if segundos >= 60 else base


def url_mrms(ts: datetime) -> str:
    return ("https://mtarchive.geol.iastate.edu/%04d/%02d/%02d/mrms/ncep/PrecipRate/"
            "PrecipRate_00.00_%s00.grib2.gz" % (ts.year, ts.month, ts.day, ts.strftime("%Y%m%d-%H%M")))


def gps_no_instante(locations: list[dict], alvo_ms: int, tol_ms: int = 3000):
    """(lat, lon, speed) interpolado em alvo_ms; None se não houver fix a <= tol_ms
    de algum dos lados (evita extrapolar)."""
    pts = sorted((p for p in locations if p.get("latitude") is not None
                  and p.get("longitude") is not None and p.get("timestamp") is not None),
                 key=lambda p: p["timestamp"])
    if not pts:
        return None
    ant = [p for p in pts if p["timestamp"] <= alvo_ms]
    pos = [p for p in pts if p["timestamp"] >= alvo_ms]
    a = ant[-1] if ant else None
    b = pos[0] if pos else None
    if a and b:
        if a["timestamp"] == b["timestamp"]:
            return (a["latitude"], a["longitude"], a.get("speed"))
        if b["timestamp"] - a["timestamp"] > 2 * tol_ms:
            return None
        f = (alvo_ms - a["timestamp"]) / (b["timestamp"] - a["timestamp"])
        return (a["latitude"] + f * (b["latitude"] - a["latitude"]),
                a["longitude"] + f * (b["longitude"] - a["longitude"]),
                a.get("speed"))
    p = a or b
    if abs(p["timestamp"] - alvo_ms) <= tol_ms:
        return (p["latitude"], p["longitude"], p.get("speed"))
    return None


def decidir(ponto, viz3x3, mais_menos_2, mais_menos_4, mais_menos_10=()):
    """Retorna (classe, ambiguo, motivo).

    ponto: mm/h no pixel (None = sem dado); viz3x3: valores 3x3 (válidos);
    mais_menos_2 / mais_menos_4: valores do ponto em t-2,t+2 / t-4,t+4 (None se ausentes);
    mais_menos_10: pontos extras (3x3 máx.) até ±10 min, usados só para exigir seco.
    """
    if ponto is None:
        return None, True, "sem_dado_mrms"
    classe = classe_de(ponto)
    viz = [v for v in viz3x3 if v is not None]
    t2 = [v for v in mais_menos_2 if v is not None]
    if classe == "seco":
        extra = [v for v in list(mais_menos_4) + list(mais_menos_10) if v is not None]
        if any(v > 0 for v in viz + t2 + extra):
            return classe, True, "seco_com_chuva_perto"
        if len(t2) < len(mais_menos_2):
            return classe, True, "seco_sem_vizinho_temporal"
        return classe, False, ""
    if len({classe_de(v) for v in viz}) > 1:
        return classe, True, "vizinhanca_heterogenea"
    if any(classe_de(v) != classe for v in t2):
        return classe, True, "instavel_2min"
    return classe, False, ""
