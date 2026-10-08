"""Replay de um evento real pelas câmeras fixas, para a demonstração."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

_DIR = Path(__file__).resolve().parents[1] / "scripts" / "coleta_fixa"
sys.path.insert(0, str(_DIR))
_spec = importlib.util.spec_from_file_location("replay_evento", _DIR / "replay_evento.py")
rp = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rp
_spec.loader.exec_module(rp)


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.fromarray((np.random.default_rng(0).random((24, 32, 3)) * 255).astype(np.uint8)).save(buf, "JPEG")
    return buf.getvalue()


def test_marca_muda_o_hash_e_preserva_os_pixels():
    original = _jpeg()
    marcado = rp.com_marca_de_replay(original, "2026-10-19T10:00:00Z")
    assert hashlib.sha256(marcado).hexdigest() != hashlib.sha256(original).hexdigest()
    assert marcado.startswith(b"\xff\xd8\xff\xfe")
    a = np.asarray(Image.open(io.BytesIO(original)))
    b = np.asarray(Image.open(io.BytesIO(marcado)))
    assert np.array_equal(a, b)
    assert rp.com_marca_de_replay(original, "x") != rp.com_marca_de_replay(original, "y")


def _par(pasta: Path, nome: str, ts: str):
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / f"{nome}.jpg").write_bytes(_jpeg())
    (pasta / f"{nome}.json").write_text(json.dumps({
        "schema": 2, "device_id": "cam1", "capturado_em_utc": ts, "arquivo": f"{nome}.jpg",
        "gps": {"latitude": -26.99, "longitude": -48.63, "ultimo_fix_em": ts, "fixo": True}}))


def test_seleciona_frames_da_camera_no_intervalo_em_ordem(tmp_path):
    raiz = tmp_path / "frames"
    _par(raiz / "cam1", "frame_b", "2026-10-01T10:05:00+00:00")
    _par(raiz / "cam1", "frame_a", "2026-10-01T10:00:00+00:00")
    _par(raiz / "cam1", "frame_c", "2026-10-01T12:00:00+00:00")
    man = tmp_path / "m.csv"
    with open(man, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["arquivo", "pasta", "ts_utc"])
        for nome, ts in [("frame_b.jpg", "2026-10-01T10:05:00Z"), ("frame_a.jpg", "2026-10-01T10:00:00Z"),
                         ("frame_c.jpg", "2026-10-01T12:00:00Z"), ("sumiu.jpg", "2026-10-01T10:01:00Z")]:
            wr.writerow([nome, "cam1", ts])
        wr.writerow(["frame_x.jpg", "outra", "2026-10-01T10:02:00Z"])
    de = datetime(2026, 10, 1, 9, tzinfo=timezone.utc)
    ate = datetime(2026, 10, 1, 11, tzinfo=timezone.utc)
    sel = rp.selecionar_frames(man, "cam1", de, ate, raiz)
    assert [p.name for p in sel] == ["frame_a.jpg", "frame_b.jpg"]


def test_prepara_frame_com_horario_atual_e_jpeg_marcado(tmp_path):
    _par(tmp_path / "orig", "frame_a", "2026-10-01T10:00:00+00:00")
    agora = datetime(2026, 10, 19, 13, 0, tzinfo=timezone.utc)
    novo = rp.preparar_frame_replay(tmp_path / "orig/frame_a.jpg", tmp_path / "tmp", agora, "m1")
    meta = json.loads(novo.with_suffix(".json").read_text())
    assert meta["capturado_em_utc"] == agora.isoformat()
    assert meta["capturado_originalmente"] == "2026-10-01T10:00:00+00:00"
    assert novo.read_bytes() != (tmp_path / "orig/frame_a.jpg").read_bytes()
