"""`demo` das últimas capturas (/cameras e /veiculos) vem de metadata.demo."""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.schemas.camera import UltimaCaptura
from app.schemas.veiculo import UltimaCapturaVeiculo


def _cap(metadata):
    return SimpleNamespace(
        id=1, captured_at=datetime(2026, 10, 14, tzinfo=timezone.utc), latitude=-23.5, longitude=-46.6,
        weather_label="garoa", confidence=0.9, modelo="m", metadata_=metadata,
    )


def test_camera_demo_vem_do_metadata():
    assert UltimaCaptura.da_captura(_cap({"demo": {"origem": "x"}})).demo is True
    assert UltimaCaptura.da_captura(_cap({"outra": 1})).demo is False
    assert UltimaCaptura.da_captura(_cap(None)).demo is False


def test_veiculo_traz_posicao_e_demo():
    u = UltimaCapturaVeiculo.da_captura(_cap({"demo": {"origem": "x"}}))
    assert (u.latitude, u.longitude, u.weather_label, u.demo) == (-23.5, -46.6, "garoa", True)
    assert UltimaCapturaVeiculo.da_captura(_cap(None)).demo is False
