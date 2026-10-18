"""Leitura de PrecipRate MRMS (grib2) em pontos, com cache em disco."""
from __future__ import annotations
import gzip, io, json, tempfile, threading, time
from pathlib import Path
import numpy as np, requests

LAT0, LON0, PASSO = 54.995, 230.005, 0.01  # centro da 1a célula (norte-oeste); lon em 0-360
NI, NJ = 7000, 3500
_lock = threading.Lock()


def indice(lat: float, lon: float):
    """(linha, coluna) da célula mais próxima, ou None se fora da grade (CONUS)."""
    lon360 = lon % 360
    i = int(round((LAT0 - lat) / PASSO)); j = int(round((lon360 - LON0) / PASSO))
    if 1 <= i < NJ - 1 and 1 <= j < NI - 1:
        return i, j
    return None


def baixar(url: str, tentativas=3):
    """Devolve bytes do grib2 descomprimido, None se 404."""
    for t in range(tentativas):
        try:
            r = requests.get(url, timeout=60, headers={"User-Agent": "cityrain-tcc-pesquisa"})
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return gzip.decompress(r.content)
        except Exception:
            time.sleep(2 * (t + 1))
    return None


def campo(grib: bytes) -> np.ndarray:
    import eccodes
    with _lock, tempfile.NamedTemporaryFile(suffix=".grib2") as f:
        f.write(grib); f.flush()
        with open(f.name, "rb") as fh:
            g = eccodes.codes_grib_new_from_file(fh)
            v = eccodes.codes_get_values(g).reshape(NJ, NI).astype("float32")
            eccodes.codes_release(g)
    return v


def janela3x3(v: np.ndarray, i: int, j: int) -> list[float]:
    """9 valores brutos (negativos = sem dado ficam como estão; filtrar com mrms_valido)."""
    return [float(x) for x in v[i - 1:i + 2, j - 1:j + 2].ravel()]
