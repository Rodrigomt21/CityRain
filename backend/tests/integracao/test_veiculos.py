"""GET /veiculos, /devices/publico só com ativos, demo em /cameras e log de ingest recusado."""

import io
import json
import logging

from PIL import Image

from app.services import inference_service as inf
from app.services.inference_service import Classificacao


def _jpeg(cor):
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), cor).save(buf, "JPEG")
    return buf.getvalue()


async def _enviar(client, chave, quando, cor, lat=-23.55, lon=-46.6, demo=False):
    meta = {"captured_at": quando, "source_type": "jetson_nano", "latitude": lat, "longitude": lon}
    if demo:
        meta["metadata"] = {"demo": {"origem": "teste"}}
    return await client.post("/api/v1/ingest", data={"metadata": json.dumps(meta)},
                             files={"image": ("f.jpg", _jpeg(cor), "image/jpeg")},
                             headers={"Authorization": f"Bearer {chave}"})


async def _classificar_garoa(monkeypatch):
    async def falso(*a, **k):
        return Classificacao("garoa", 0.8, "movel_v3", "ep1")

    monkeypatch.setattr(inf.roteador_inferencia, "classificar", falso)


async def test_veiculos_lista_moveis_ativos_com_ultima_captura(client, criar_device, monkeypatch):
    await _classificar_garoa(monkeypatch)
    carro, chave = await criar_device("jetson-veic")
    cam, _ = await criar_device("fixa-veic", tipo="fixa", latitude=-24.0, longitude=-46.3)
    await _enviar(client, chave, "2026-10-14T10:00:00Z", (201, 11, 31))
    r2 = await _enviar(client, chave, "2026-10-14T10:01:00Z", (202, 12, 32), lat=-23.56, lon=-46.61)
    assert r2.status_code == 201, r2.text

    veiculos = (await client.get("/api/v1/veiculos/")).json()
    ids = {v["id"] for v in veiculos}
    assert carro["id"] in ids and cam["id"] not in ids
    v = next(x for x in veiculos if x["id"] == carro["id"])
    u = v["ultima_captura"]
    assert u["id"] == r2.json()["id"]
    assert (u["latitude"], u["longitude"], u["weather_label"], u["demo"]) == (-23.56, -46.61, "garoa", False)
    assert "vehicle_plate" not in v and "imagem_url" not in v


async def test_veiculos_excluir_demo_e_flag_demo(client, criar_device, monkeypatch):
    await _classificar_garoa(monkeypatch)
    carro, chave = await criar_device("jetson-demo")
    real = await _enviar(client, chave, "2026-10-14T10:00:00Z", (203, 13, 33))
    await _enviar(client, chave, "2026-10-14T10:05:00Z", (204, 14, 34), demo=True)

    com_demo = next(x for x in (await client.get("/api/v1/veiculos/")).json() if x["id"] == carro["id"])
    assert com_demo["ultima_captura"]["demo"] is True
    sem_demo = next(x for x in (await client.get("/api/v1/veiculos/?excluir_demo=true")).json()
                    if x["id"] == carro["id"])
    assert sem_demo["ultima_captura"]["id"] == real.json()["id"]
    assert sem_demo["ultima_captura"]["demo"] is False


async def test_veiculo_desativado_some_das_rotas_publicas(client, criar_device, admin_headers):
    carro, _ = await criar_device("jetson-desativado")
    r = await client.delete(f"/api/v1/devices/{carro['id']}", headers=admin_headers)
    assert r.status_code == 204
    publicos = {d["id"] for d in (await client.get("/api/v1/devices/publico")).json()}
    veiculos = {v["id"] for v in (await client.get("/api/v1/veiculos/")).json()}
    assert carro["id"] not in publicos and carro["id"] not in veiculos
    # a listagem de admin continua com todos
    admin = {d["id"] for d in (await client.get("/api/v1/devices/", headers=admin_headers)).json()}
    assert carro["id"] in admin


async def test_cameras_marca_demo_na_ultima_captura(client, criar_device, monkeypatch):
    async def falso(*a, **k):
        return Classificacao("forte", 0.7, "fixa_f1", "ep7")

    monkeypatch.setattr(inf.roteador_inferencia, "classificar", falso)
    cam, chave = await criar_device("fixa-flag-demo", tipo="fixa", latitude=-24.0, longitude=-46.3)
    meta = {"captured_at": "2026-10-14T10:00:00Z", "source_type": "x", "metadata": {"demo": {"origem": "t"}}}
    r = await client.post("/api/v1/ingest", data={"metadata": json.dumps(meta)},
                          files={"image": ("f.jpg", _jpeg((205, 15, 35)), "image/jpeg")},
                          headers={"Authorization": f"Bearer {chave}"})
    assert r.status_code == 201, r.text
    c = next(x for x in (await client.get("/api/v1/cameras/")).json() if x["id"] == cam["id"])
    assert c["ultima_captura"]["demo"] is True


async def test_ingest_recusado_fica_no_log(client, criar_device, caplog):
    _, chave = await criar_device("jetson-log")
    with caplog.at_level(logging.WARNING):
        # JSON inválido: recusa dentro do endpoint (400), com o device identificado
        r = await client.post("/api/v1/ingest", data={"metadata": "{nao-e-json"},
                              headers={"Authorization": f"Bearer {chave}"})
        assert r.status_code == 400
        # sem o campo metadata: recusa na validação do FastAPI (422), antes do endpoint
        r = await client.post("/api/v1/ingest", data={}, headers={"Authorization": f"Bearer {chave}"})
        assert r.status_code == 422
    textos = [m.getMessage() for m in caplog.records]
    assert any("ingest recusado (400)" in t and "jetson-log" in t for t in textos), textos
    assert any("ingest recusado (422)" in t and "metadata" in t for t in textos), textos
