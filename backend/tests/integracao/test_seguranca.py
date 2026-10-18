"""Endurecimento da API (auditoria de 18/10/2026): o que é público não vaza, e o upload é validado pelo conteúdo."""

import io
import json

from PIL import Image

from app.services import inference_service as inf
from app.services.inference_service import Classificacao


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (9, 9, 9)).save(buf, "PNG")
    return buf.getvalue()


def _meta(**extra):
    return json.dumps({"captured_at": "2026-10-18T12:00:00Z", "latitude": -23.55, "longitude": -46.63,
                       "source_type": "jetson_nano", **extra})


async def _falso(*a, **k):
    return Classificacao("garoa", 0.8, "m", "ep1")


async def test_arquivo_que_nao_e_imagem_e_422(client, criar_device, monkeypatch):
    monkeypatch.setattr(inf.roteador_inferencia, "classificar", _falso)
    _, chave = await criar_device("jetson-seg")
    r = await client.post("/api/v1/ingest", data={"metadata": _meta()},
                          files={"image": ("x.jpg", b"<?php echo 1; ?>", "image/jpeg")},
                          headers={"Authorization": f"Bearer {chave}"})
    assert r.status_code == 422


async def test_png_declarado_como_jpeg_e_aceito_pelo_conteudo(client, criar_device, monkeypatch):
    monkeypatch.setattr(inf.roteador_inferencia, "classificar", _falso)
    _, chave = await criar_device("jetson-png")
    r = await client.post("/api/v1/ingest", data={"metadata": _meta()},
                          files={"image": ("../../evil.exe", _png(), "image/jpeg")},
                          headers={"Authorization": f"Bearer {chave}"})
    assert r.status_code == 201
    det = (await client.get(f"/api/v1/captures/{r.json()['id']}")).json()
    mf = det["media_files"][0]
    assert mf["mime_type"] == "image/png"
    assert "file_path" not in mf  # caminho no disco do servidor não é público


async def test_detalhe_publico_sem_mensagem_de_erro_interna(client, criar_device, monkeypatch):
    monkeypatch.setattr(inf.roteador_inferencia, "classificar", _falso)
    _, chave = await criar_device("jetson-log")
    r = await client.post("/api/v1/ingest", data={"metadata": _meta()},
                          files={"image": ("f.png", _png(), "image/png")},
                          headers={"Authorization": f"Bearer {chave}"})
    det = (await client.get(f"/api/v1/captures/{r.json()['id']}")).json()
    assert det["ingestion_logs"] and all("error_message" not in log for log in det["ingestion_logs"])


async def test_metadata_grande_ou_nao_objeto_e_recusado(client, criar_device):
    _, chave = await criar_device("jetson-meta")
    h = {"Authorization": f"Bearer {chave}"}
    grande = _meta(metadata={"lixo": "x" * 20_000})
    assert (await client.post("/api/v1/ingest", data={"metadata": grande}, headers=h)).status_code == 413
    assert (await client.post("/api/v1/ingest", data={"metadata": "[1, 2]"}, headers=h)).status_code == 400


async def test_admin_key_errada_e_401(client):
    r = await client.get("/api/v1/devices/", headers={"Authorization": "Bearer chave-errada"})
    assert r.status_code == 401
