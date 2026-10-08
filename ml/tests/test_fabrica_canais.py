"""Primeira convolução de 6 canais começa equivalente à de 3."""

import sys
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cityrain_ml.models.fabrica import construir  # noqa: E402


@pytest.mark.parametrize("arq", ["mobilenet_v3_small", "efficientnet_b0", "resnet18"])
def test_seis_canais_aceita_entrada_e_comeca_igual(arq):
    torch.manual_seed(0)
    m3 = construir(arq, 4, pretreinado=False).eval()
    m6 = construir(arq, 4, pretreinado=False, canais_entrada=6).eval()
    m6.load_state_dict({k: v for k, v in m3.state_dict().items() if v.shape == m6.state_dict()[k].shape}, strict=False)
    x = torch.randn(2, 3, 64, 64)
    ref = torch.randn(2, 3, 64, 64)
    with torch.no_grad():
        # copiar os pesos da 1ª conv de m3 para os 3 primeiros canais de m6 (o que a fábrica faz com ImageNet)
        conv3 = next(mm for mm in m3.modules() if isinstance(mm, torch.nn.Conv2d))
        conv6 = next(mm for mm in m6.modules() if isinstance(mm, torch.nn.Conv2d))
        assert conv6.in_channels == 6
        assert torch.all(conv6.weight[:, 3:] == 0)
        conv6.weight[:, :3] = conv3.weight
        assert torch.allclose(m3(x), m6(torch.cat([x, ref], 1)), atol=1e-5)


def test_canais_invalidos():
    with pytest.raises(ValueError):
        construir("mobilenet_v3_small", 4, pretreinado=False, canais_entrada=4)


@pytest.mark.parametrize("arq", ["mobilenet_v3_small", "efficientnet_b0", "resnet18"])
def test_seis_canais_preserva_pesos_originais_da_primeira_conv(arq):
    torch.manual_seed(7)
    m3 = construir(arq, 4, pretreinado=False)
    torch.manual_seed(7)
    m6 = construir(arq, 4, pretreinado=False, canais_entrada=6)
    conv3 = next(mm for mm in m3.modules() if isinstance(mm, torch.nn.Conv2d))
    conv6 = next(mm for mm in m6.modules() if isinstance(mm, torch.nn.Conv2d))
    assert torch.equal(conv6.weight[:, :3], conv3.weight)
    assert torch.all(conv6.weight[:, 3:] == 0)
