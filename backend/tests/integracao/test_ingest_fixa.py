"""Ingestão de câmera fixa: posição do cadastro, imagem obrigatória, modelo registrado."""

import io
import json

from PIL import Image

from app.services import inference_service as inf
from app.services.inference_service import Classificacao


def _jpeg(cor=(100, 110, 120)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), cor).save(buf, "JPEG")
    return buf.getvalue()


def _meta(**kw):
    base = {"captured_at": "2026-10-08T15:00:00Z", "source_type": "qualquer"}
    return {"metadata": json.dumps({**base, **kw})}


async def _fixa(criar_device):
    return await criar_device("fixa-cam", tipo="fixa", latitude=-23.5465, longitude=-46.6340,
                              stream_url="https://youtube.com/watch?v=x", descricao="Centro de SP")


async def test_cadastro_de_fixa_exige_posicao(client, admin_headers):
    r = await client.post("/api/v1/devices/", json={"name": "fixa-sem-pos", "tipo": "fixa"}, headers=admin_headers)
    assert r.status_code == 422


async def test_cadastro_devolve_tipo_e_posicao(criar_device):
    corpo, _ = await _fixa(criar_device)
    assert corpo["tipo"] == "fixa" and corpo["latitude"] == -23.5465


async def test_fixa_sem_imagem_e_recusada(client, criar_device):
    _, chave = await _fixa(criar_device)
    r = await client.post("/api/v1/ingest", data=_meta(), headers={"Authorization": f"Bearer {chave}"})
    assert r.status_code == 422
    assert "imagem" in r.json()["detail"].lower()


async def test_fixa_usa_posicao_do_cadastro_e_registra_modelo(client, criar_device, monkeypatch):
    async def falso(image_bytes, tipo, device_name, quando):
        assert tipo == "fixa"
        return Classificacao("moderado", 0.81, "fixa_f3", "ep7")

    monkeypatch.setattr(inf.roteador_inferencia, "classificar", falso)
    _, chave = await _fixa(criar_device)
    r = await client.post(
        "/api/v1/ingest",
        data=_meta(latitude=0.0, longitude=0.0),
        files={"image": ("f.jpg", _jpeg((1, 2, 3)), "image/jpeg")},
        headers={"Authorization": f"Bearer {chave}"},
    )
    assert r.status_code == 201, r.text
    c = r.json()
    assert (c["latitude"], c["longitude"]) == (-23.5465, -46.6340)
    assert c["source_type"] == "camera_fixa"
    assert (c["weather_label"], c["modelo"], c["modelo_versao"]) == ("moderado", "fixa_f3", "ep7")


async def test_movel_continua_exigindo_lat_lon_do_json(client, criar_device):
    _, chave = await criar_device("jetson")
    r = await client.post("/api/v1/ingest", data=_meta(), headers={"Authorization": f"Bearer {chave}"})
    assert r.status_code == 400


async def test_movel_sem_imagem_continua_seco(client, criar_device):
    _, chave = await criar_device("jetson-seco")
    r = await client.post("/api/v1/ingest", data=_meta(latitude=-23.5, longitude=-46.6),
                          headers={"Authorization": f"Bearer {chave}"})
    assert r.status_code == 201 and r.json()["weather_label"] == "seco"
    assert r.json()["modelo"] is None
