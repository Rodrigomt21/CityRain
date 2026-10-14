"""Coletor de câmeras fixas: contrato de arquivo igual ao da Jetson."""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_P = Path(__file__).resolve().parents[1] / "scripts" / "coleta_fixa" / "coletor.py"
_spec = importlib.util.spec_from_file_location("coletor", _P)
col = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = col
_spec.loader.exec_module(col)

JPEG = b"\xff\xd8\xff\xe0" + b"x" * 100


def _fonte(**kw):
    base = {"id": "cam1", "tipo": "snapshot", "url": "http://x/shot.jpg", "lat": -23.5, "lon": -46.6}
    return col.carregar_fontes({"fontes": [{**base, **kw}]})[0]


def test_grava_par_no_contrato_da_jetson(tmp_path):
    quando = datetime(2026, 10, 4, 22, 19, 50, 951000, tzinfo=timezone.utc)
    jpg = col.gravar_frame(JPEG, _fonte(), tmp_path, quando)
    assert jpg.name == "frame_20261004_221950_951.jpg"
    meta = json.loads(jpg.with_suffix(".json").read_text())
    assert meta["capturado_em_utc"] == quando.isoformat()
    assert meta["gps"] == {"latitude": -23.5, "longitude": -46.6, "ultimo_fix_em": quando.isoformat(), "fixo": True}
    assert jpg.read_bytes() == JPEG
    assert not list(tmp_path.rglob("*.tmp"))


def test_descarta_frame_repetido(tmp_path):
    f = _fonte()
    t = datetime.now(timezone.utc)
    assert col.gravar_frame(JPEG, f, tmp_path, t) is not None
    assert col.gravar_frame(JPEG, f, tmp_path, t) is None
    assert col.gravar_frame(JPEG + b"y", f, tmp_path, t) is not None


def test_fonte_inativa_e_tipo_invalido():
    assert col.carregar_fontes({"fontes": [{"id": "a", "tipo": "camera", "lat": 0, "lon": 0, "ativa": False}]}) == []
    with pytest.raises(ValueError):
        _fonte(tipo="ftp")


def test_falha_de_uma_fonte_nao_para_as_outras(tmp_path, monkeypatch):
    fontes = col.carregar_fontes({"fontes": [
        {"id": "ruim", "tipo": "snapshot", "url": "u", "lat": 0, "lon": 0},
        {"id": "boa", "tipo": "camera", "lat": 0, "lon": 0},
    ]})
    monkeypatch.setitem(col.CAPTURAS, "snapshot", lambda f: (_ for _ in ()).throw(RuntimeError("fora do ar")))
    monkeypatch.setitem(col.CAPTURAS, "camera", lambda f: JPEG)
    col.rodada(fontes, tmp_path, forcar=True)
    assert fontes[0].falhas == 1 and fontes[0].proxima > fontes[1].proxima
    assert len(list((tmp_path / "boa").glob("*.jpg"))) == 1


def test_janelas_com_chuva_une_margem_e_respeita_raio_e_dvr():
    sys.path.insert(0, str(_P.parent))
    from recuperar_dvr import janelas_com_chuva

    f = _fonte()  # -23.5, -46.6
    perto = {"lat": "-23.51", "lon": "-46.60", "janela_min": "10"}  # ~1 km
    longe = {"lat": "-23.70", "lon": "-46.60", "janela_min": "10"}  # ~22 km
    L = [
        {**perto, "ts_utc": "2026-10-04T17:10:00Z", "acumulado_mm": "1.0"},
        {**perto, "ts_utc": "2026-10-04T17:40:00Z", "acumulado_mm": "0.4"},   # une com a anterior pela margem
        {**perto, "ts_utc": "2026-10-04T20:00:00Z", "acumulado_mm": "0.0"},   # sem chuva: ignora
        {**longe, "ts_utc": "2026-10-04T12:00:00Z", "acumulado_mm": "9.0"},   # fora do raio
    ]
    dvr0 = datetime(2026, 10, 4, 16, 50, tzinfo=timezone.utc)
    j = janelas_com_chuva(f, L, 5.0, timedelta(minutes=15), dvr0)
    assert j == [(dvr0, datetime(2026, 10, 4, 17, 55, tzinfo=timezone.utc))]  # corta no início do DVR


class _Resp:
    def __init__(self, status):
        self.status_code = status


class _SessaoFalsa:
    def __init__(self, status=201, erro=None):
        self.status, self.erro, self.chamadas = status, erro, []

    def post(self, url, files=None, data=None, headers=None, timeout=None):
        self.chamadas.append({"url": url, "files": files, "data": data, "headers": headers})
        if self.erro:
            raise self.erro
        return _Resp(self.status)


def test_nome_device_segue_convencao():
    assert col.nome_device("sp_centro_geolan") == "fixa-sp_centro_geolan"


def test_token_da_variavel_tem_precedencia(tmp_path, monkeypatch):
    arq = tmp_path / "tokens.json"
    arq.write_text(json.dumps({"cam1": "do-arquivo"}))
    assert col.token_da_fonte("cam1", arq) == "do-arquivo"
    monkeypatch.setenv("CITYRAIN_TOKEN_CAM1", "da-env")
    assert col.token_da_fonte("cam1", arq) == "da-env"
    assert col.token_da_fonte("outra", arq) is None
    assert col.token_da_fonte("cam1", tmp_path / "nao_existe.json") == "da-env"


def test_metadados_do_ingest(tmp_path):
    quando = datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc)
    jpg = col.gravar_frame(JPEG, _fonte(), tmp_path, quando)
    meta = col.metadados_ingest(json.loads(jpg.with_suffix(".json").read_text()))
    assert meta["captured_at"] == quando.isoformat()
    assert (meta["latitude"], meta["longitude"]) == (-23.5, -46.6)
    assert meta["source_type"] == "camera_fixa"
    assert meta["metadata"]["fonte"] == "cam1"
    assert "demo" not in meta["metadata"]
    com_demo = col.metadados_ingest(json.loads(jpg.with_suffix(".json").read_text()), demo={"origem": "x"})
    assert com_demo["metadata"]["demo"] == {"origem": "x"}


def test_enviar_frame_faz_post_multipart(tmp_path):
    jpg = col.gravar_frame(JPEG, _fonte(), tmp_path, datetime.now(timezone.utc))
    s = _SessaoFalsa(201)
    assert col.enviar_frame(jpg, "http://api/api/v1/ingest", "tok", sessao=s) == 201
    ch = s.chamadas[0]
    assert ch["headers"] == {"Authorization": "Bearer tok"}
    assert ch["files"]["image"][2] == "image/jpeg"
    assert json.loads(ch["data"]["metadata"])["source_type"] == "camera_fixa"


def test_enviar_frame_com_rede_fora_devolve_zero(tmp_path):
    import requests

    jpg = col.gravar_frame(JPEG, _fonte(), tmp_path, datetime.now(timezone.utc))
    s = _SessaoFalsa(erro=requests.ConnectionError("sem rede"))
    assert col.enviar_frame(jpg, "http://api", "tok", sessao=s) == 0
    assert jpg.exists()


def test_carrega_campos_novos_da_fonte():
    f = _fonte(posicao_verificada=True, fonte_publica="https://exemplo.gov.br/cameras")
    assert f.posicao_verificada is True and f.fonte_publica.startswith("https://")
    assert _fonte().posicao_verificada is False


def test_rodada_envia_com_token_e_so_grava_sem_token(tmp_path, monkeypatch, capsys):
    fontes = col.carregar_fontes({"fontes": [
        {"id": "com", "tipo": "camera", "lat": 0, "lon": 0},
        {"id": "sem", "tipo": "camera", "lat": 0, "lon": 0},
    ]})
    monkeypatch.setitem(col.CAPTURAS, "camera", lambda f: JPEG + f.id.encode())
    chamadas = []

    def falso(jpg, url, token, **kw):
        chamadas.append((jpg.name, url, token, kw))
        return 201

    monkeypatch.setattr(col, "enviar_frame", falso)
    col.rodada(fontes, tmp_path, forcar=True, envio={"url": "http://api/ingest", "tokens": {"com": "tok"}})
    saida = capsys.readouterr().out
    assert len(chamadas) == 1 and chamadas[0][1:3] == ("http://api/ingest", "tok")
    assert chamadas[0][3] == {"timeout": 10}                      # envio ao vivo não espera 30 s
    assert "com:" in saida and "ingest 201" in saida
    assert saida.count("ingest") == 1                             # a fonte sem token só gravou
    assert len(list((tmp_path / "sem").glob("*.jpg"))) == 1


def test_main_enviar_sem_backend_url_da_erro_claro(tmp_path, monkeypatch):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("fontes:\n  - {id: x, tipo: camera, lat: 0, lon: 0}\n")
    monkeypatch.setattr(sys, "argv", ["coletor", str(cfg), "--enviar", "--uma-rodada"])
    with pytest.raises(SystemExit) as e:
        col.main()
    assert "backend_url" in str(e.value)


# ------------------------------------------------------------------ cache da URL do HLS e paralelismo
URL_EXP = "https://manifest.googlevideo.com/api/manifest/hls_playlist/expire/2000/ei/x/id/abc.1/itag/95/"


def test_expira_em_le_os_dois_formatos():
    assert col.expira_em(URL_EXP) == 2000.0
    assert col.expira_em("https://h/p.m3u8?a=1&expire=123&b=2") == 123.0
    assert col.expira_em("https://h/p.m3u8") is None


def test_hls_valido_respeita_idade_e_expire():
    assert not col.hls_valido("", 0, 100)
    assert col.hls_valido(URL_EXP, 0, 100, margem_s=300)
    assert not col.hls_valido(URL_EXP, 0, 1800, margem_s=300)          # faltam 200 s < margem
    assert not col.hls_valido("https://h/p.m3u8", 0, 4000, max_idade_s=3600)  # sem expire: vale a idade
    assert col.hls_valido("https://h/p.m3u8", 0, 3000, max_idade_s=3600)


def test_youtube_reusa_url_e_renova_se_ffmpeg_falhar(monkeypatch):
    f = _fonte(tipo="youtube")
    f.hls, f.hls_em = "https://h/p.m3u8", time.time()
    chamadas = []

    def falso(cmd, **kw):
        chamadas.append(cmd[0])
        if cmd[0] == "ffmpeg":
            Path(cmd[-1]).write_bytes(JPEG)
        return type("R", (), {"returncode": 0, "stdout": "https://h/novo.m3u8\n", "stderr": ""})()

    monkeypatch.setattr(col.subprocess, "run", falso)
    assert col._jpeg_youtube(f) == JPEG
    assert chamadas == ["ffmpeg"]  # cache quente: nada de yt-dlp
    f.hls_em = time.time() - 2 * col.RENOVAR_HLS_S
    col._jpeg_youtube(f)
    assert chamadas == ["ffmpeg", "yt-dlp", "ffmpeg"] and f.hls == "https://h/novo.m3u8"


def test_rodada_captura_em_paralelo(tmp_path, monkeypatch):
    fontes = col.carregar_fontes({"fontes": [
        {"id": f"c{i}", "tipo": "camera", "lat": 0, "lon": 0} for i in range(4)]})

    def lenta(f):
        time.sleep(0.3)
        return JPEG + f.id.encode()

    monkeypatch.setitem(col.CAPTURAS, "camera", lenta)
    t0 = time.time()
    col.rodada(fontes, tmp_path, forcar=True)
    assert time.time() - t0 < 0.9  # sequencial levaria 1,2 s
    assert all(len(list((tmp_path / f.id).glob("*.jpg"))) == 1 and not f.ocupada for f in fontes)
