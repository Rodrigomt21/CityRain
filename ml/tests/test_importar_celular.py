"""Importador de fotos/vídeos de celular (EXIF e ffprobe)."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

_P = Path(__file__).resolve().parents[1] / "scripts" / "coleta_fixa" / "importar_celular.py"
_spec = importlib.util.spec_from_file_location("importar_celular", _P)
imp = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = imp
_spec.loader.exec_module(imp)


def _foto(caminho: Path, com_gps: bool = True, offset: str | None = "-03:00") -> None:
    img = Image.fromarray((np.random.default_rng(0).random((40, 60, 3)) * 255).astype(np.uint8))
    exif = img.getexif()
    sub = exif.get_ifd(0x8769)
    sub[0x9003] = "2026:10:04 15:30:10"  # DateTimeOriginal (local)
    if offset:
        sub[0x9011] = offset  # OffsetTimeOriginal
    if com_gps:
        gps = exif.get_ifd(0x8825)
        gps[1], gps[2] = "S", (23.0, 33.0, 1.8)   # 23°33'01.8"S
        gps[3], gps[4] = "W", (46.0, 38.0, 0.0)   # 46°38'00"W
    img.save(caminho, exif=exif)


def test_foto_com_gps_vira_par_em_utc(tmp_path):
    _foto(tmp_path / "IMG_1.jpg")
    destino = tmp_path / "saida"
    rel = imp.importar(tmp_path, destino, "-03:00", 2.0)
    assert rel["importados"] == ["frame_20261004_183010_000.jpg"]  # 15:30 em -03:00 = 18:30Z
    meta = json.loads((destino / "frame_20261004_183010_000.json").read_text())
    assert meta["gps"]["latitude"] == pytest.approx(-23.5505, abs=1e-4)
    assert meta["gps"]["longitude"] == pytest.approx(-46.6333, abs=1e-4)
    assert meta["capturado_em_utc"] == "2026-10-04T18:30:10+00:00"


def test_sem_offset_usa_fuso_padrao(tmp_path):
    _foto(tmp_path / "IMG_2.jpg", offset=None)
    lat, lon, quando = imp.ler_foto(tmp_path / "IMG_2.jpg", "-02:00")
    assert quando == datetime(2026, 10, 4, 17, 30, 10, tzinfo=timezone.utc)


def test_foto_sem_gps_e_pulada_nunca_inventada(tmp_path):
    _foto(tmp_path / "IMG_3.jpg", com_gps=False)
    rel = imp.importar(tmp_path, tmp_path / "saida", "-03:00", 2.0)
    assert rel["importados"] == [] and rel["pulados_sem_gps_ou_hora"] == ["IMG_3.jpg"]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="sem ffmpeg")
def test_video_com_location_extrai_frames_com_horario(tmp_path):
    mp4 = tmp_path / "VID.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=64x48:rate=10:duration=5",
                    "-metadata", "location=-23.5505-046.6333/", "-metadata", "creation_time=2026-10-04T18:00:00Z",
                    "-movflags", "use_metadata_tags", str(mp4)], check=True)
    rel = imp.importar(tmp_path, tmp_path / "saida", "-03:00", 2.0)
    assert rel["importados"][:2] == ["frame_20261004_180000_000.jpg", "frame_20261004_180002_000.jpg"]
