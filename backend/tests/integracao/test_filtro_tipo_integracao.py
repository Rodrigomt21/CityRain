"""GET /captures?tipo= separa câmera fixa de Jetson."""

import io
import json

from PIL import Image

from app.services import inference_service as inf
from app.services.inference_service import Classificacao


def _jpeg(cor):
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), cor).save(buf, "JPEG")
    return buf.getvalue()


async def test_filtro_separa_os_dominios(client, criar_device, monkeypatch):
    async def falso(*a, **k):
        return Classificacao("garoa", 0.9, "m", "ep1")

    monkeypatch.setattr(inf.roteador_inferencia, "classificar", falso)
    fixa, kf = await criar_device("fx", tipo="fixa", latitude=-23.0, longitude=-46.0)
    movel, km = await criar_device("mv")
    meta_f = {"metadata": json.dumps({"captured_at": "2026-10-08T15:00:00Z", "source_type": "x"})}
    meta_m = {"metadata": json.dumps({"captured_at": "2026-10-08T15:00:00Z", "source_type": "jetson", "latitude": -23.1, "longitude": -46.1})}
    await client.post("/api/v1/ingest", data=meta_f, files={"image": ("a.jpg", _jpeg((9, 9, 9)), "image/jpeg")}, headers={"Authorization": f"Bearer {kf}"})
    await client.post("/api/v1/ingest", data=meta_m, files={"image": ("b.jpg", _jpeg((8, 8, 8)), "image/jpeg")}, headers={"Authorization": f"Bearer {km}"})

    so_fixa = (await client.get("/api/v1/captures/", params={"tipo": "fixa", "limit": 200})).json()
    so_movel = (await client.get("/api/v1/captures/", params={"tipo": "movel", "limit": 200})).json()
    assert fixa["id"] in {c["device_id"] for c in so_fixa}
    assert movel["id"] not in {c["device_id"] for c in so_fixa}
    assert fixa["id"] not in {c["device_id"] for c in so_movel}
