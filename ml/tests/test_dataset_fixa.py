"""Dataset e partições do modelo fixo, sem PyTorch."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cityrain_ml.data.fixa import CLASSES_FIXA, DatasetFixa, papeis_ircnn, particoes_fixa, preparar_par, subamostrar  # noqa: E402

FOLDS = [["ircnn__e1", "ircnn__e2"], ["ircnn__e3", "ircnn__e4"]]


def R(particao, classe, camera="a", ev="a__1", ref="ml/r.jpg", caminho=None, ts=""):
    return {"caminho": caminho or f"ml/{camera}/{ev}/{classe}{np.random.randint(1e9)}.jpg", "classe": classe, "mm_h": "0",
            "particao": particao, "origem": "irCNN" if camera == "ircnn" else "live", "evento_id": ev,
            "camera": camera, "periodo": "dia", "ts_utc": ts, "referencia": ref, "metodo_rotulo": "x"}


def _cfg(fold=0, com_ref=False, maximo=200):
    return {"dados": {"com_referencia": com_ref, "ircnn_cv": {"fold": fold, "max_por_evento": maximo, "folds": FOLDS}}}


def test_papeis_ircnn_fold_e_final():
    p = papeis_ircnn({"fold": 0, "folds": FOLDS})
    assert p["test"] == {"ircnn__e1", "ircnn__e2"} and p["val"] == {"ircnn__e3"} and p["train"] == {"ircnn__e4"}
    f = papeis_ircnn({"fold": "final", "folds": FOLDS})
    assert f["test"] == set() and f["val"] == {"ircnn__e1"} and f["train"] == {"ircnn__e2", "ircnn__e3", "ircnn__e4"}


def test_particoes_juntam_lives_e_ircnn_pelo_fold():
    linhas = [R("train", "garoa"), R("val", "seco", ev="a__2"), R("test_camera", "forte", camera="bc", ev="bc__1"),
              R("ircnn", "forte", camera="ircnn", ev="ircnn__e1"), R("ircnn", "forte", camera="ircnn", ev="ircnn__e3"),
              R("ircnn", "moderada", camera="ircnn", ev="ircnn__e4"), R("referencia", "seco")]
    parts, info = particoes_fixa(linhas, _cfg())
    assert {r["evento_id"] for r in parts["train"]} == {"a__1", "ircnn__e4"}
    assert {r["evento_id"] for r in parts["val"]} == {"a__2", "ircnn__e3"}
    assert {r["evento_id"] for r in parts["test_ircnn"]} == {"ircnn__e1"}
    assert len(parts["test_camera"]) == 1 and parts["test_prospectivo"] == []
    assert info["descartadas_sem_referencia"] == 0


def test_com_referencia_descarta_e_conta():
    linhas = [R("train", "garoa"), R("train", "seco", ref="")]
    parts, info = particoes_fixa(linhas, _cfg(com_ref=True))
    assert len(parts["train"]) == 1 and info["descartadas_sem_referencia"] == 1


def test_camera_de_teste_no_treino_e_erro():
    linhas = [R("train", "garoa", camera="bc"), R("test_camera", "forte", camera="bc", ev="bc__1")]
    with pytest.raises(ValueError, match="bc"):
        particoes_fixa(linhas, _cfg())


def test_subamostrar_por_evento_e_classe():
    linhas = [R("ircnn", "forte", camera="ircnn", ev="ircnn__e4", caminho=f"ml/x/t{i}.jpg") for i in range(10)]
    s = subamostrar(linhas, 3)
    assert [r["caminho"] for r in s] == ["ml/x/t0.jpg", "ml/x/t4.jpg", "ml/x/t9.jpg"]  # ordem pelo número do arquivo


def _img(p: Path, cor):
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 48), cor).save(p)


def test_dataset_com_referencia_tem_seis_canais_e_metades_corretas(tmp_path):
    _img(tmp_path / "ml/f.jpg", (255, 0, 0))
    _img(tmp_path / "ml/r.jpg", (0, 0, 255))
    linhas = [{"caminho": "ml/f.jpg", "referencia": "ml/r.jpg", "classe": "forte"}]
    ds = DatasetFixa(linhas, tmp_path, CLASSES_FIXA, 24, 32, com_referencia=True)
    x, y = ds[0]
    assert x.shape == (6, 24, 32) and y == 3
    assert x[0].mean() > x[2].mean()      # metade 1 = imagem vermelha
    assert x[5].mean() > x[3].mean()      # metade 2 = referência azul


def test_dataset_sem_referencia_tem_tres_canais(tmp_path):
    _img(tmp_path / "ml/f.jpg", (0, 255, 0))
    ds = DatasetFixa([{"caminho": "ml/f.jpg", "referencia": "", "classe": "seco"}], tmp_path, CLASSES_FIXA, 24, 32)
    x, y = ds[0]
    assert x.shape == (3, 24, 32) and y == 0


def test_aumentacao_pareada_aplica_o_mesmo_recorte(tmp_path):
    arr = np.zeros((48, 64, 3), np.uint8)
    arr[:, :32] = 255
    Image.fromarray(arr).save(tmp_path / "f.jpg")
    Image.fromarray(arr).save(tmp_path / "r.jpg")
    ds = DatasetFixa([{"caminho": "f.jpg", "referencia": "r.jpg", "classe": "garoa"}], tmp_path, CLASSES_FIXA, 24, 32,
                     aumentacao={"flip_horizontal": True, "recorte_escala_min": 0.6, "brilho_contraste": 0.0}, com_referencia=True)
    for ep in range(5):
        ds.epoca = ep
        x, _ = ds[0]
        assert np.allclose(x[:3], x[3:], atol=0.05)


def test_preparar_par_concatena_imagem_primeiro():
    a, b = Image.new("RGB", (8, 8), (255, 255, 255)), Image.new("RGB", (8, 8), (0, 0, 0))
    x = preparar_par(a, b, 8, 8)
    assert x.shape == (6, 8, 8) and x[:3].mean() > x[3:].mean()
