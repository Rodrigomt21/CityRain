"""Lista de câmeras fixas, série e imagem da captura."""

import io
import json
from pathlib import Path

from PIL import Image

from app.services import inference_service as inf
from app.services.inference_service import Classificacao


def _jpeg(cor):
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), cor).save(buf, "JPEG")
    return buf.getvalue()


async def _enviar(client, chave, quando, cor, demo=False):
    meta = {"captured_at": quando, "source_type": "x"}
    if demo:
        meta["metadata"] = {"demo": {"origem": "teste"}}
    return await client.post("/api/v1/ingest", data={"metadata": json.dumps(meta)},
                             files={"image": ("f.jpg", _jpeg(cor), "image/jpeg")},
                             headers={"Authorization": f"Bearer {chave}"})


async def test_lista_so_fixas_com_ultima_captura(client, criar_device, monkeypatch):
    async def falso(*a, **k):
        return Classificacao("forte", 0.7, "fixa_f1", "ep7")

    monkeypatch.setattr(inf.roteador_inferencia, "classificar", falso)
    cam, chave = await criar_device("fixa-lista", tipo="fixa", latitude=-24.0, longitude=-46.3, descricao="Santos")
    jet, _ = await criar_device("jetson-lista")
    await _enviar(client, chave, "2026-10-08T15:00:00Z", (1, 1, 1))
    r2 = await _enviar(client, chave, "2026-10-08T15:01:00Z", (2, 2, 2))

    cams = (await client.get("/api/v1/cameras/")).json()
    ids = {c["id"] for c in cams}
    assert cam["id"] in ids and jet["id"] not in ids
    c = next(x for x in cams if x["id"] == cam["id"])
    assert c["ultima_captura"]["id"] == r2.json()["id"]
    assert c["ultima_captura"]["weather_label"] == "forte"
    assert c["imagem_url"] == f"/api/v1/captures/{r2.json()['id']}/imagem"


async def test_camera_sem_captura_tem_campos_nulos(client, criar_device):
    cam, _ = await criar_device("fixa-vazia", tipo="fixa", latitude=-24.0, longitude=-46.3)
    c = next(x for x in (await client.get("/api/v1/cameras/")).json() if x["id"] == cam["id"])
    assert c["ultima_captura"] is None and c["imagem_url"] is None


async def test_excluir_demo_pula_capturas_de_demonstracao(client, criar_device, monkeypatch):
    async def falso(*a, **k):
        return Classificacao("garoa", 0.6, "m", "ep1")

    monkeypatch.setattr(inf.roteador_inferencia, "classificar", falso)
    cam, chave = await criar_device("fixa-demo", tipo="fixa", latitude=-24.0, longitude=-46.3)
    real = await _enviar(client, chave, "2026-10-08T15:00:00Z", (3, 3, 3))
    await _enviar(client, chave, "2026-10-08T15:05:00Z", (4, 4, 4), demo=True)
    c = next(x for x in (await client.get("/api/v1/cameras/", params={"excluir_demo": True})).json() if x["id"] == cam["id"])
    assert c["ultima_captura"]["id"] == real.json()["id"]


async def test_serie_em_ordem_crescente(client, criar_device, monkeypatch):
    async def falso(*a, **k):
        return Classificacao("garoa", 0.6, "m", "ep1")

    monkeypatch.setattr(inf.roteador_inferencia, "classificar", falso)
    cam, chave = await criar_device("fixa-serie", tipo="fixa", latitude=-24.0, longitude=-46.3)
    from datetime import datetime, timedelta, timezone

    agora = datetime.now(timezone.utc)
    for i, cor in enumerate([(5, 5, 5), (6, 6, 6)]):
        await _enviar(client, chave, (agora - timedelta(minutes=10 - i)).isoformat(), cor)
    serie = (await client.get(f"/api/v1/cameras/{cam['id']}/serie", params={"horas": 1})).json()
    tempos = [p["captured_at"] for p in serie]
    assert len(serie) == 2 and tempos == sorted(tempos)


async def test_serie_de_device_movel_e_404(client, criar_device):
    jet, _ = await criar_device("jetson-serie")
    assert (await client.get(f"/api/v1/cameras/{jet['id']}/serie")).status_code == 404


async def test_imagem_da_captura_e_404_se_sumiu_do_disco(client, criar_device, monkeypatch, db):
    async def falso(*a, **k):
        return Classificacao("garoa", 0.6, "m", "ep1")

    monkeypatch.setattr(inf.roteador_inferencia, "classificar", falso)
    _, chave = await criar_device("fixa-img", tipo="fixa", latitude=-24.0, longitude=-46.3)
    cap = (await _enviar(client, chave, "2026-10-08T15:00:00Z", (7, 7, 7))).json()
    ok = await client.get(f"/api/v1/captures/{cap['id']}/imagem")
    assert ok.status_code == 200 and ok.headers["content-type"].startswith("image/")
    assert ok.headers["cache-control"] == "public, max-age=86400, immutable"
    det = (await client.get(f"/api/v1/captures/{cap['id']}")).json()
    Path(det["media_files"][0]["file_path"]).unlink()
    assert (await client.get(f"/api/v1/captures/{cap['id']}/imagem")).status_code == 404


async def test_imagem_de_captura_do_carro_e_404(client, criar_device, monkeypatch):
    """Privacidade (LGPD): frames da Jetson no carro nunca são servidos publicamente."""
    async def falso(*a, **k):
        return Classificacao("garoa", 0.6, "m", "ep1")

    monkeypatch.setattr(inf.roteador_inferencia, "classificar", falso)
    _, chave = await criar_device("jetson-privacidade")
    meta = {"captured_at": "2026-10-08T15:00:00Z", "source_type": "x", "latitude": -23.5, "longitude": -46.6}
    r = await client.post("/api/v1/ingest", data={"metadata": json.dumps(meta)},
                          files={"image": ("f.jpg", _jpeg((11, 13, 17)), "image/jpeg")},
                          headers={"Authorization": f"Bearer {chave}"})
    assert r.status_code in (200, 201), r.text
    assert (await client.get(f"/api/v1/captures/{r.json()['id']}/imagem")).status_code == 404
