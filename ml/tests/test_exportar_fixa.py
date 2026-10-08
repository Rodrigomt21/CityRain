import csv
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

torch = pytest.importorskip("torch")
ort = pytest.importorskip("onnxruntime")
onnx = pytest.importorskip("onnx")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cityrain_ml.models.fabrica import construir  # noqa: E402

_P = Path(__file__).resolve().parents[1] / "scripts" / "treino" / "exportar_onnx_fixa.py"
_spec = importlib.util.spec_from_file_location("exportar_onnx_fixa", _P)
ex = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ex
_spec.loader.exec_module(ex)

COLS = ["caminho", "classe", "mm_h", "particao", "origem", "evento_id", "camera", "periodo", "ts_utc", "referencia", "metodo_rotulo"]


@pytest.mark.parametrize("canais", [3, 6])
def test_exporta_com_metadados_paridade_e_referencias(tmp_path, canais):
    (tmp_path / "ml/img").mkdir(parents=True)
    Image.new("RGB", (40, 30), (200, 200, 200)).save(tmp_path / "ml/img/ref.jpg")
    Image.new("RGB", (40, 30), (20, 30, 40)).save(tmp_path / "ml/img/f.jpg")
    linhas = [
        {"caminho": "ml/img/ref.jpg", "classe": "seco", "particao": "referencia", "origem": "live", "camera": "cam1", "periodo": "dia", "referencia": ""},
        {"caminho": "ml/img/f.jpg", "classe": "forte", "particao": "test_camera", "origem": "live", "camera": "cam1", "periodo": "dia", "referencia": "ml/img/ref.jpg"},
    ]
    with open(tmp_path / "ml/s.csv", "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=COLS)
        wr.writeheader()
        for r in linhas:
            wr.writerow({k: r.get(k, "") for k in COLS})
    cfg = {"nome": "t", "dados": {"splits_csv": "ml/s.csv", "com_referencia": canais == 6},
           "entrada": {"altura": 32, "largura": 32}, "modelo": {"arquitetura": "mobilenet_v3_small"}}
    m = construir("mobilenet_v3_small", 4, pretreinado=False, canais_entrada=canais)
    ckpt = tmp_path / "melhor.pt"
    torch.save({"estado": m.state_dict(), "epoca": 3, "config": cfg, "classes": ["seco", "garoa", "moderada", "forte"], "canais_entrada": canais}, ckpt)

    destino = tmp_path / "fixa.onnx"
    info = ex.exportar_fixa(ckpt, destino)
    meta = ort.InferenceSession(str(destino)).get_modelmeta().custom_metadata_map
    assert json.loads(meta["classes"])[0] == "seco" and meta["canais_entrada"] == str(canais)
    assert meta["referencia"] == ("mesma_camera_mesmo_periodo" if canais == 6 else "nenhuma")
    assert ex.conferir_paridade_fixa(info, destino, tmp_path) < 1e-4
    refs = ex.copiar_referencias(tmp_path / "ml/s.csv", tmp_path, tmp_path / "refs")
    assert refs == [tmp_path / "refs/fixa-cam1/dia.jpg"] and refs[0].is_file()


def test_copiar_referencias_recusa_periodo_invalido(tmp_path):
    (tmp_path / "ml").mkdir()
    (tmp_path / "ml/r.jpg").write_bytes(b"x")
    with open(tmp_path / "ml/s.csv", "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=COLS)
        wr.writeheader()
        wr.writerow({"caminho": "ml/r.jpg", "classe": "seco", "particao": "referencia", "origem": "live",
                     "camera": "cam1", "periodo": "madrugada"})
    with pytest.raises(ValueError, match="madrugada"):
        ex.copiar_referencias(tmp_path / "ml/s.csv", tmp_path, tmp_path / "refs")
