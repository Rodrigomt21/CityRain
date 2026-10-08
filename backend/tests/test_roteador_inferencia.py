"""Roteamento de inferência por tipo de dispositivo, com ONNX de brinquedo."""

import asyncio
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper
from PIL import Image

from app.services.inference_service import Classificacao, InferenceService, RoteadorInferencia


def _onnx(caminho: Path, classes: list[str], canais: int, vencedora: int, experimento: str) -> Path:
    """Modelo que ignora a imagem e devolve logits com `vencedora` no topo."""
    k = len(classes)
    logits = np.full((1, k), -5.0, dtype=np.float32)
    logits[0, vencedora] = 5.0
    entrada = helper.make_tensor_value_info("imagem", TensorProto.FLOAT, ["n", canais, 8, 8])
    saida = helper.make_tensor_value_info("logits", TensorProto.FLOAT, ["n", k])
    # ReduceMean(imagem) * 0 + logits: usa a entrada (o runtime exige) sem mudar a saída
    nos = [
        helper.make_node("ReduceMean", ["imagem"], ["m"], axes=[1, 2, 3], keepdims=0),
        helper.make_node("Mul", ["m", "zero"], ["m0"]),
        helper.make_node("Unsqueeze", ["m0", "eixo"], ["m1"]),
        helper.make_node("Add", ["m1", "base"], ["logits"]),
    ]
    inits = [
        helper.make_tensor("zero", TensorProto.FLOAT, [], [0.0]),
        helper.make_tensor("eixo", TensorProto.INT64, [1], [1]),
        helper.make_tensor("base", TensorProto.FLOAT, [1, k], logits.flatten().tolist()),
    ]
    g = helper.make_graph(nos, "brinquedo", [entrada], [saida], inits)
    m = helper.make_model(g, opset_imports=[helper.make_opsetid("", 13)])
    meta = {"classes": json.dumps(classes), "altura": "8", "largura": "8",
            "media": json.dumps([0.5, 0.5, 0.5]), "desvio": json.dumps([0.5, 0.5, 0.5]),
            "experimento": experimento, "epoca": "7"}
    if canais != 3:
        meta["canais_entrada"] = str(canais)
    for chave, valor in meta.items():
        p = m.metadata_props.add()
        p.key, p.value = chave, valor
    onnx.save(m, caminho)
    return caminho


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 24), (120, 130, 140)).save(buf, "JPEG")
    return buf.getvalue()


QUANDO = datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc)  # dia


def _roteador(tmp_path, canais_fixa=3, com_referencia=True):
    movel = InferenceService(_onnx(tmp_path / "m.onnx", ["garoa", "moderada", "forte"], 3, 2, "movel_v3"))
    fixa = InferenceService(_onnx(tmp_path / "f.onnx", ["seco", "garoa", "moderada", "forte"], canais_fixa, 0, "fixa_f1"))
    refs = tmp_path / "refs"
    if com_referencia:
        (refs / "fixa-cam1").mkdir(parents=True)
        (refs / "fixa-cam1" / "noite.jpg").write_bytes(_jpeg())
    return RoteadorInferencia(movel, fixa, refs)


def test_movel_usa_modelo_movel(tmp_path):
    c = asyncio.run(_roteador(tmp_path).classificar(_jpeg(), "movel", "jetson-1", QUANDO))
    assert c.label == "forte" and c.modelo == "movel_v3" and c.versao == "ep7"


def test_fixa_usa_modelo_fixo_e_pode_devolver_seco(tmp_path):
    c = asyncio.run(_roteador(tmp_path).classificar(_jpeg(), "fixa", "fixa-cam1", QUANDO))
    assert c.label == "seco" and c.modelo == "fixa_f1"


def test_moderada_do_ml_vira_moderado_do_banco(tmp_path):
    s = InferenceService(_onnx(tmp_path / "x.onnx", ["seco", "garoa", "moderada", "forte"], 3, 2, "x"))
    assert asyncio.run(s.classificar(_jpeg())).label == "moderado"


def test_fixa_com_seis_canais_usa_referencia_do_outro_periodo_quando_falta(tmp_path):
    r = _roteador(tmp_path, canais_fixa=6)   # só existe noite.jpg; QUANDO é dia
    c = asyncio.run(r.classificar(_jpeg(), "fixa", "fixa-cam1", QUANDO))
    assert c.label == "seco"


def test_fixa_com_seis_canais_sem_referencia_fica_nao_medida(tmp_path):
    r = _roteador(tmp_path, canais_fixa=6, com_referencia=False)
    assert asyncio.run(r.classificar(_jpeg(), "fixa", "fixa-cam1", QUANDO)) == Classificacao.vazia()


def test_modelo_fixo_ausente_nao_afeta_o_movel(tmp_path):
    movel = InferenceService(_onnx(tmp_path / "m.onnx", ["garoa", "moderada", "forte"], 3, 1, "movel_v3"))
    r = RoteadorInferencia(movel, InferenceService(tmp_path / "nao_existe.onnx"), tmp_path)
    assert asyncio.run(r.classificar(_jpeg(), "fixa", "fixa-cam1", QUANDO)) == Classificacao.vazia()
    assert asyncio.run(r.classificar(_jpeg(), "movel", "j", QUANDO)).label == "moderado"


def test_classify_antigo_continua_devolvendo_par(tmp_path):
    s = InferenceService(_onnx(tmp_path / "m.onnx", ["garoa", "moderada", "forte"], 3, 0, "v3"))
    label, conf = asyncio.run(s.classify(_jpeg()))
    assert label == "garoa" and 0 < conf <= 1
