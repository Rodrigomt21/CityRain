"""Inferência ONNX do modelo de intensidade (sem banco)."""

import asyncio
import io

import numpy as np
import pytest
from PIL import Image

from app.services.inference_service import MODELO_PADRAO, RAIN_LABELS, InferenceService

pytestmark = pytest.mark.skipif(not MODELO_PADRAO.is_file(), reason="modelo ONNX não está no repo")


def _jpeg(seed: int = 0, tamanho=(640, 480)) -> bytes:
    arr = (np.random.default_rng(seed).random((tamanho[1], tamanho[0], 3)) * 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, "JPEG")
    return buf.getvalue()


def test_carrega_modelo_e_le_preprocessamento_dos_metadados():
    s = InferenceService(MODELO_PADRAO)
    assert s.disponivel
    assert s._model.classes == ["garoa", "moderado", "forte"]  # traduzido para o vocabulário do banco
    assert (s._model.altura, s._model.largura) == (288, 384)


def test_classifica_com_label_do_banco_e_confianca_valida():
    label, conf = asyncio.run(InferenceService(MODELO_PADRAO).classify(_jpeg()))
    assert label in RAIN_LABELS
    assert 1 / 3 <= conf <= 1.0


def test_aceita_qualquer_resolucao_e_png():
    s = InferenceService(MODELO_PADRAO)
    buf = io.BytesIO()
    Image.open(io.BytesIO(_jpeg(1, (1280, 720)))).save(buf, "PNG")
    assert asyncio.run(s.classify(buf.getvalue()))[0] in RAIN_LABELS


def test_imagem_corrompida_vira_nao_medida_sem_erro():
    assert asyncio.run(InferenceService(MODELO_PADRAO).classify(b"isto nao e imagem")) == (None, None)


def test_sem_modelo_devolve_nao_medida(tmp_path):
    s = InferenceService(tmp_path / "nao_existe.onnx")
    assert not s.disponivel
    assert asyncio.run(s.classify(_jpeg())) == (None, None)


def test_modelo_corrompido_nao_derruba_o_app(tmp_path):
    ruim = tmp_path / "ruim.onnx"
    ruim.write_bytes(b"lixo")
    assert not InferenceService(ruim).disponivel
