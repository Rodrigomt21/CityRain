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


def test_periodo_local_fronteiras_dia_06h00_e_18h30_locais():
    utc = timezone.utc
    assert rp.periodo_local(datetime(2026, 10, 1, 8, 59, tzinfo=utc)) == "noite"   # 05:59 local
    assert rp.periodo_local(datetime(2026, 10, 1, 9, 0, tzinfo=utc)) == "dia"      # 06:00 local
    assert rp.periodo_local(datetime(2026, 10, 1, 21, 29, tzinfo=utc)) == "dia"    # 18:29 local
    assert rp.periodo_local(datetime(2026, 10, 1, 21, 30, tzinfo=utc)) == "noite"  # 18:30 local


def test_instante_sem_fuso_assume_menos_tres():
    t, assumido = rp.parse_instante("2026-10-01T18:00:00", "--de")
    assert assumido and t.utcoffset().total_seconds() == -3 * 3600
    t, assumido = rp.parse_instante("2026-10-01T18:00:00Z", "--de")
    assert not assumido and t.hour == 18


def test_instante_malformado_levanta_valueerror_claro():
    import pytest
    with pytest.raises(ValueError, match="--ate"):
        rp.parse_instante("ontem", "--ate")


def _frames(tmp_path, n=3):
    out = []
    for i in range(n):
        _par(tmp_path, f"f{i}", f"2026-10-01T10:0{i}:00+00:00")
        out.append(tmp_path / f"f{i}.jpg")
    return out


def test_envio_resume_ok_duplicado_erro_e_sem_rede(tmp_path):
    frames = _frames(tmp_path, 4)
    status = iter([200, 409, 500, 0])
    r = rp.enviar_todos(frames, "u", "t", "cam1", 0, enviar=lambda *a, **k: next(status), dormir=lambda s: None)
    assert (r["ok"], r["duplicados"], r["erros"], r["sem_rede"]) == (1, 1, 1, 1)
    assert r["abortado"] is None


def test_envio_aborta_no_primeiro_4xx_exceto_409(tmp_path):
    frames = _frames(tmp_path, 3)
    chamadas = []

    def falso(*a, **k):
        chamadas.append(1)
        return 401

    r = rp.enviar_todos(frames, "u", "t", "cam1", 0, enviar=falso, dormir=lambda s: None)
    assert len(chamadas) == 1
    assert r["abortado"] == 401


def test_envio_nao_dorme_depois_do_ultimo_frame(tmp_path):
    frames = _frames(tmp_path, 3)
    pausas = []
    rp.enviar_todos(frames, "u", "t", "cam1", 2.0, enviar=lambda *a, **k: 200, dormir=pausas.append)
    assert pausas == [2.0, 2.0]


def test_periodos_dos_frames_le_o_horario_original(tmp_path):
    _par(tmp_path, "dia", "2026-10-01T15:00:00+00:00")     # 12:00 local
    _par(tmp_path, "noite", "2026-10-01T23:00:00+00:00")   # 20:00 local
    assert rp.periodos_dos_frames([tmp_path / "dia.jpg", tmp_path / "noite.jpg"]) == {"dia", "noite"}


def test_main_sem_frames_sai_com_codigo_diferente_de_zero(tmp_path, monkeypatch):
    import pytest
    man = tmp_path / "m.csv"
    man.write_text("arquivo,pasta,ts_utc\n")
    tok = tmp_path / "t.json"
    tok.write_text('{"cam1": "x"}')
    monkeypatch.setattr(sys, "argv", ["r", "--camera", "cam1", "--manifest", str(man),
                                      "--raiz-frames", str(tmp_path), "--tokens", str(tok), "--api", "http://x"])
    with pytest.raises(SystemExit) as e:
        rp.main()
    assert e.value.code not in (0, None)
    assert "manifest" in str(e.value.code)


def test_main_aborta_se_periodo_diferente_do_atual_sem_forcar(tmp_path, monkeypatch):
    import pytest
    raiz = tmp_path / "frames"
    _par(raiz / "cam1", "f0", "2026-10-01T23:00:00+00:00")   # noite
    man = tmp_path / "m.csv"
    man.write_text("arquivo,pasta,ts_utc\nf0.jpg,cam1,2026-10-01T23:00:00Z\n")
    tok = tmp_path / "t.json"
    tok.write_text('{"cam1": "x"}')
    monkeypatch.setattr(rp, "periodo_agora", lambda: "dia")
    monkeypatch.setattr(rp, "enviar_frame", lambda *a, **k: pytest.fail("não deveria enviar"))
    monkeypatch.setattr(sys, "argv", ["r", "--camera", "cam1", "--manifest", str(man), "--raiz-frames", str(raiz),
                                      "--tokens", str(tok), "--api", "http://x"])
    with pytest.raises(SystemExit) as e:
        rp.main()
    assert "--forcar-periodo" in str(e.value.code)
