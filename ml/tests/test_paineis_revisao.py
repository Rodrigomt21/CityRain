"""Amostragem para revisão visual e leitura das exclusões marcadas."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from PIL import Image

_P = Path(__file__).resolve().parents[1] / "scripts" / "dataset" / "paineis_revisao_fixa.py"
_spec = importlib.util.spec_from_file_location("paineis_revisao_fixa", _P)
pr = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = pr
_spec.loader.exec_module(pr)


def _linhas():
    out = []
    for cam in ("a", "b"):
        for i in range(50):
            out.append({"pasta": cam, "arquivo": f"f{i:03d}.jpg", "classe": "garoa" if i % 2 else "seco"})
    out.append({"pasta": "a", "arquivo": "x.jpg", "classe": ""})
    return out


def test_amostra_por_camera_e_classe_e_deterministica():
    g1 = pr.amostrar_por_grupo(_linhas(), 10, seed=0)
    g2 = pr.amostrar_por_grupo(_linhas(), 10, seed=0)
    assert set(g1) == {("a", "garoa"), ("a", "seco"), ("b", "garoa"), ("b", "seco")}
    assert all(len(v) == 10 for v in g1.values())
    assert g1 == g2


def test_grupo_pequeno_vem_inteiro():
    linhas = [{"pasta": "c", "arquivo": "u.jpg", "classe": "forte"}]
    assert len(pr.amostrar_por_grupo(linhas, 24, 0)[("c", "forte")]) == 1


def test_painel_tem_celula_para_cada_imagem(tmp_path):
    caminhos = []
    for i in range(7):
        p = tmp_path / f"{i}.jpg"
        Image.new("RGB", (64, 48), (i * 30, 0, 0)).save(p)
        caminhos.append(p)
    caminhos.append(tmp_path / "nao_existe.jpg")
    painel = pr.montar_painel(caminhos, colunas=4, lado=50)
    assert painel.size == (4 * 50, 2 * 50)


def test_le_exclusoes_marcadas(tmp_path):
    csv_path = tmp_path / "revisao.csv"
    csv_path.write_text(
        "pasta,arquivo,camera,classe,manifest,excluir,motivo\n"
        "a,f1.jpg,a,garoa,m.csv,1,congelada\n"
        "a,f2.jpg,a,garoa,m.csv,,\n"
        "b,f3.jpg,b,seco,m.csv,sim,tampada\n"
    )
    assert pr.ler_exclusoes(csv_path) == {("a", "f1.jpg"), ("b", "f3.jpg")}
    assert pr.ler_exclusoes(tmp_path / "nao_existe.csv") == set()


def test_manifest_5km_amostra_so_moderada_e_forte():
    linhas = [{"pasta": "a", "arquivo": f"{c}{i}.jpg", "classe": c} for c in ("seco", "garoa", "moderada", "forte") for i in range(3)]
    g = pr.amostrar_por_grupo(linhas, 10, 0, classes={"moderada", "forte"})
    assert set(g) == {("a", "moderada"), ("a", "forte")}
    assert pr.classes_do_manifest("manifest_coleta_fixa_5km.csv") == {"moderada", "forte"}
    assert pr.classes_do_manifest("manifest_coleta_fixa.csv") is None
