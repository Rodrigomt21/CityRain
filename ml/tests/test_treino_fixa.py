"""Treino de ponta a ponta do modelo fixo num dataset minúsculo (CPU, ~1 min)."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest
import yaml
from PIL import Image

pytest.importorskip("torch")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cityrain_ml.training.fixa import agregar_cv_fixa, executar_fixa  # noqa: E402

COLS = ["caminho", "classe", "mm_h", "particao", "origem", "evento_id", "camera", "periodo", "ts_utc", "referencia", "metodo_rotulo"]
CORES = {"seco": (200, 200, 200), "garoa": (150, 150, 170), "moderada": (90, 90, 120), "forte": (30, 30, 60)}
FOLDS = [["ircnn__e1"], ["ircnn__e2"]]


def _montar(tmp: Path, com_ref: bool) -> Path:
    linhas = []
    for cam, part in [("a", "train"), ("a2", "val"), ("bc", "test_camera")]:
        for classe, cor in CORES.items():
            for i in range(3):
                p = f"ml/img/{cam}_{classe}_{i}.jpg"
                (tmp / p).parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (40, 30), cor).save(tmp / p)
                linhas.append({"caminho": p, "classe": classe, "mm_h": "1", "particao": part, "origem": "live",
                               "evento_id": f"{cam}__1", "camera": cam, "periodo": "dia", "ts_utc": "",
                               "referencia": "ml/img/ref.jpg", "metodo_rotulo": "x"})
    for ev in ("ircnn__e1", "ircnn__e2"):
        for classe, cor in CORES.items():
            p = f"ml/img/{ev}_{classe}.jpg"
            Image.new("RGB", (40, 30), cor).save(tmp / p)
            linhas.append({"caminho": p, "classe": classe, "mm_h": "1", "particao": "ircnn", "origem": "irCNN",
                           "evento_id": ev, "camera": "ircnn", "periodo": "noite", "ts_utc": "",
                           "referencia": "ml/img/ref.jpg", "metodo_rotulo": "x"})
    Image.new("RGB", (40, 30), (210, 210, 210)).save(tmp / "ml/img/ref.jpg")
    csv_path = tmp / "ml/splits.csv"
    with open(csv_path, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=COLS)
        wr.writeheader()
        wr.writerows(linhas)
    cfg = {"nome": "teste_fixa", "seed": 0,
           "dados": {"splits_csv": "ml/splits.csv", "com_referencia": com_ref,
                     "ircnn_cv": {"fold": 0, "max_por_evento": 50, "folds": FOLDS}},
           "entrada": {"altura": 32, "largura": 32},
           "modelo": {"arquitetura": "mobilenet_v3_small", "pretreinado": False},
           "aumentacao": {"flip_horizontal": True, "recorte_escala_min": 0.9, "brilho_contraste": 0.0},
           "treino": {"dispositivo": "cpu", "epocas": 2, "batch": 8, "lr": 0.001, "weight_decay": 0.0,
                      "label_smoothing": 0.0, "paciencia": 5, "workers": 0}}
    cfg_path = tmp / "cfg.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg))
    return cfg_path


@pytest.mark.parametrize("com_ref", [False, True])
def test_treina_avalia_e_agrega(tmp_path, com_ref):
    cfg_path = _montar(tmp_path, com_ref)
    runs = [executar_fixa(cfg_path, tmp_path, fold=k) for k in (0, 1)]
    for run in runs:
        met = json.loads((run / "metricas.json").read_text())
        assert set(met["particoes"]) >= {"val", "test_ircnn", "test_camera", "test_prospectivo"}
        assert met["particoes"]["test_prospectivo"] == {"n": 0}
        assert met["particoes"]["test_camera"]["n"] == 12
        cab = (run / "predicoes_test_camera.csv").read_text().splitlines()[0]
        assert "p_seco" in cab and "p_forte" in cab
    import torch

    assert torch.load(runs[0] / "melhor.pt", weights_only=False)["canais_entrada"] == (6 if com_ref else 3)
    agg = agregar_cv_fixa(runs, tmp_path / "agg")
    assert agg["test_ircnn_agregado"]["n"] == 8          # 2 eventos x 4 classes, cada um testado uma vez
    assert "media" in agg["test_camera"]["resumo.f1_macro"]
