import importlib.util
import sys
from pathlib import Path

import numpy as np

_P = Path(__file__).resolve().parents[1] / "scripts" / "avaliacao" / "avaliar_v3_em_fixa.py"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_spec = importlib.util.spec_from_file_location("avaliar_v3_em_fixa", _P)
f0 = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = f0
_spec.loader.exec_module(f0)


def test_ignora_seco_e_usa_tres_classes():
    linhas = [{"classe": c, "camera": "a", "periodo": "dia", "evento_id": "e", "mm_h": "1"} for c in ("seco", "garoa", "forte")]
    probs = np.array([[0.9, 0.05, 0.05], [0.8, 0.1, 0.1], [0.1, 0.1, 0.8]])
    m = f0.metricas_v3_em_fixa(linhas, probs)
    assert m["n"] == 2 and m["resumo"]["acuracia"] == 1.0
    assert m["resumo"]["matriz_confusao"]["classes"] == ["garoa", "moderada", "forte"]
