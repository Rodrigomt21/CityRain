"""CLI de comparação pareada entre dois experimentos (sem PyTorch)."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_P = Path(__file__).resolve().parents[1] / "scripts" / "avaliacao" / "comparar_fixa.py"
_spec = importlib.util.spec_from_file_location("comparar_fixa", _P)
cmp = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = cmp
_spec.loader.exec_module(cmp)

C = ("seco", "garoa", "moderada", "forte")
COLS = ["caminho", "classe", "mm_h", "evento_id", "camera", "periodo", "pred", "p_seco", "p_garoa", "p_moderada", "p_forte", "score"]


def _fold(raiz: Path, nome: str, eventos: list[str], acerta_forte: bool, prefixo_caminho: str = "f") -> Path:
    run = raiz / nome
    run.mkdir(parents=True)
    with open(run / "predicoes_test_ircnn.csv", "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(COLS)
        for ev in eventos:
            for classe in ("seco", "forte"):
                pred = classe if (classe == "seco" or acerta_forte) else "seco"
                p = [0.01] * 4
                p[C.index(pred)] = 0.97
                wr.writerow([f"{prefixo_caminho}/{ev}/{classe}.jpg", classe, "0", ev, "ircnn", "dia", pred, *p, "0"])
    return run


def _exp(raiz: Path, nome: str, acerta_forte: bool, prefixo: str = "f") -> list[Path]:
    return [_fold(raiz, f"{nome}_fold{k}__x", [f"e{2 * k}", f"e{2 * k + 1}"], acerta_forte, prefixo) for k in range(2)]


def test_compara_pareado_e_salva(tmp_path):
    a = _exp(tmp_path, "a", True)
    b = _exp(tmp_path, "b", False)
    r = cmp.comparar(a, b, n=100, seed=0)
    assert r["n_linhas"] == 8 and r["n_eventos"] == 4
    assert r["diferenca_f1_macro"]["media"] > 0 and r["diferenca_recall_forte"]["media"] > 0
    destino = cmp.salvar(r, "a", "b", tmp_path / "res")
    assert destino.name == "fixa_comparacao_a_vs_b.json"
    assert json.loads(destino.read_text())["diferenca_f1_macro"]["ic95"]


def test_aceita_diretorio_de_cv(tmp_path):
    a = _exp(tmp_path, "a", True)
    cv = tmp_path / "a__cv_1"
    cv.mkdir()
    (cv / "metricas_cv.json").write_text(json.dumps({"folds": [p.name for p in a]}))
    assert cmp.resolver_runs([cv]) == a


def test_conjuntos_de_frames_diferentes_dao_erro(tmp_path):
    a = _exp(tmp_path, "a", True)
    b = _exp(tmp_path, "b", True, prefixo="outro")
    with pytest.raises(ValueError, match="caminho"):
        cmp.comparar(a, b, n=5, seed=0)
