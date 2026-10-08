# Câmera fixa — Plano C: Modelo fixo (4 classes)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Treinar, comparar (F0 a F3) e exportar o modelo de câmera fixa de 4 classes (`seco`, `garoa`, `moderada`, `forte`), só com dado real, com validação por evento e por câmera.

**Architecture:** Um módulo de treino **novo** (`cityrain_ml/training/fixa.py`) em vez de mexer no `training/intensidade.py` que gerou o v3 de produção. Reaproveita a fábrica de modelos, a normalização e as métricas. A lógica sem torch (partições, dataset, métricas) fica em módulos testáveis no CI; a parte com torch é fina. A variante F3 recebe 6 canais: o frame e uma referência seca da mesma câmera no mesmo período do dia.

**Tech Stack:** PyTorch + torchvision (MobileNetV3-Large, EfficientNet-B0), NumPy, Pillow, PyYAML, onnx + onnxruntime, pytest.

**Spec:** `docs/specs/spec-camera-fixa.md` (seção CF5). Consome o CSV do Plano B (`ml/data/splits/fixa_v1.csv`); produz o ONNX que o Plano A (Task 3) carrega.

## Global Constraints

- **Sintético nunca entra** no modelo fixo.
- Classes, nesta ordem: `("seco", "garoa", "moderada", "forte")`. O score ordinal é `Σ p_k·k` com k = 0..3.
- Época escolhida pela validação, **nunca** pelo teste. Modelo final com o número de épocas da mediana da CV e fica a última época (como no v3).
- Validação cruzada por evento do irCNN com os **mesmos 4 folds** do `treino_intensidade_cv_v3_mnv3.yaml`.
- Pré-processamento idêntico ao do backend: PIL RGB → resize bilinear para 288×384 → /255 → normalização ImageNet; com referência, cada metade é preparada igual e as duas são concatenadas nos canais (imagem primeiro).
- Código sem torch em `cityrain_ml/data/fixa.py` e `cityrain_ml/evaluation/fixa.py` (o CI do ML roda sem torch). Testes que precisam de torch usam `pytest.importorskip("torch")`.
- Python do ML: `ml/.venv/bin/python`. Treinos longos só com o Rodrigo presente, de dia, com `caffeinate -i`, um fold por job.
- Commits `tipo: descrição` em português, terminando com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Sem push.

## Review Focus

1. **Linha sem referência num experimento com referência** → descartada antes do treino e contada no `historico.json` (`descartadas_sem_referencia`), nunca um tensor de zeros silencioso (Task 3).
2. **Partição de teste vazia** (ex.: `test_prospectivo` antes de 13/10) → a avaliação pula a partição e registra `"n": 0`, sem quebrar (Task 4).
3. **Classe ausente na verdade de uma partição** (ex.: sem `forte` na câmera de teste) → F1 macro só sobre classes presentes e `recall_forte` = `null` em vez de 0 (Task 1).
4. **Checkpoint de 3 canais exportado como se fosse de 6** (ou o contrário) → o exportador lê `canais_entrada` do checkpoint e a paridade falha alto se divergir (Task 6).
5. **Câmera de teste aparecendo no treino** → o treino falha com erro explícito se alguma linha `train`/`val` tiver `camera == camera_teste` do CSV (Task 4).

---

## File Structure

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `ml/src/cityrain_ml/evaluation/metricas.py` | modificar | `kappa_quadratico`, `acuracia_chuva_vs_seco`, `recall_classe` |
| `ml/src/cityrain_ml/evaluation/fixa.py` | criar | métricas por partição, por câmera e por período; bootstrap por evento |
| `ml/src/cityrain_ml/models/fabrica.py` | modificar | `canais_entrada` (3 ou 6) |
| `ml/src/cityrain_ml/data/fixa.py` | criar | `CLASSES_FIXA`, partições do treino com CV do irCNN, `DatasetFixa` com referência pareada |
| `ml/src/cityrain_ml/training/fixa.py` | criar | treinar, avaliar, agregar CV, executar |
| `ml/scripts/treino/treinar_fixa.py` | criar | CLI |
| `ml/configs/treino_fixa_f1_mnv3.yaml`, `treino_fixa_f2_effb0.yaml`, `treino_fixa_f3_mnv3_ref.yaml` | criar | experimentos |
| `ml/scripts/avaliacao/avaliar_v3_em_fixa.py` | criar | F0: v3 de produção nas câmeras fixas |
| `ml/scripts/treino/exportar_onnx_fixa.py` | criar | ONNX + referências para o backend |
| `ml/tests/test_metricas_fixa.py`, `test_dataset_fixa.py`, `test_fabrica_canais.py`, `test_treino_fixa.py`, `test_f0_v3.py`, `test_exportar_fixa.py` | criar | testes |

---

### Task 1: Métricas do modelo fixo

**Files:**
- Modify: `ml/src/cityrain_ml/evaluation/metricas.py`
- Create: `ml/src/cityrain_ml/evaluation/fixa.py`
- Test: `ml/tests/test_metricas_fixa.py`

**Interfaces:**
- Produces (todas NumPy puro):
  - `kappa_quadratico(y_true, y_pred, n_classes) -> float` (QWK; `nan` com menos de 2 classes na verdade).
  - `acuracia_chuva_vs_seco(y_true, y_pred, idx_seco=0) -> float` (acerto de "choveu ou não").
  - `recall_classe(m: np.ndarray, k: int) -> float | None` (`None` se a classe não aparece na verdade).
  - `metricas_particao(linhas: list[dict], probs: np.ndarray, classes: Sequence[str]) -> dict` com chaves `n`, `resumo` (de `resumo_classificacao`), `qwk`, `acuracia_chuva_vs_seco`, `recall_forte`, `spearman_score_mm_h`, `por_periodo` (`{"dia": {...}, "noite": {...}}` com `n`, `f1_macro`, `acuracia`), `por_camera` (mesmo formato). Linhas com classe fora de `classes` são ignoradas. `n == 0` → `{"n": 0}`.
  - `bootstrap_eventos(linhas, probs, classes, n=1000, seed=0) -> dict` com `f1_macro` e `recall_forte`, cada um `{"media", "ic95": [lo, hi]}`, reamostrando **eventos** (`evento_id`) com reposição.

- [ ] **Step 1: Testes que falham** (`ml/tests/test_metricas_fixa.py`)

```python
"""Métricas do modelo de câmera fixa (NumPy puro)."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cityrain_ml.evaluation.fixa import bootstrap_eventos, metricas_particao  # noqa: E402
from cityrain_ml.evaluation.metricas import acuracia_chuva_vs_seco, kappa_quadratico, matriz_confusao, recall_classe  # noqa: E402

C = ("seco", "garoa", "moderada", "forte")


def _probs(preds, k=4):
    p = np.full((len(preds), k), 0.01)
    p[np.arange(len(preds)), preds] = 0.97
    return p


def test_qwk_perfeito_e_um():
    assert kappa_quadratico([0, 1, 2, 3], [0, 1, 2, 3], 4) == 1.0


def test_qwk_pune_mais_o_erro_distante():
    perto = kappa_quadratico([0, 1, 2, 3, 3], [0, 1, 2, 3, 2], 4)
    longe = kappa_quadratico([0, 1, 2, 3, 3], [0, 1, 2, 3, 0], 4)
    assert perto > longe


def test_qwk_com_uma_classe_so_e_nan():
    assert math.isnan(kappa_quadratico([1, 1], [1, 1], 4))


def test_acuracia_chuva_vs_seco_ignora_intensidade():
    assert acuracia_chuva_vs_seco([0, 1, 3, 2], [0, 3, 1, 0]) == 0.75


def test_recall_de_classe_ausente_e_none():
    m = matriz_confusao([0, 1], [0, 1], 4)
    assert recall_classe(m, 3) is None
    assert recall_classe(m, 1) == 1.0


def _linha(classe, cam="a", periodo="dia", ev="a__1", mm="0"):
    return {"classe": classe, "camera": cam, "periodo": periodo, "evento_id": ev, "mm_h": mm}


def test_metricas_particao_tem_recortes():
    linhas = [_linha("seco"), _linha("forte", mm="20"), _linha("garoa", cam="b", periodo="noite", mm="1")]
    m = metricas_particao(linhas, _probs([0, 3, 1]), C)
    assert m["n"] == 3 and m["resumo"]["acuracia"] == 1.0
    assert m["recall_forte"] == 1.0
    assert set(m["por_camera"]) == {"a", "b"} and set(m["por_periodo"]) == {"dia", "noite"}
    assert m["spearman_score_mm_h"] > 0.9


def test_metricas_particao_vazia():
    assert metricas_particao([], np.zeros((0, 4)), C) == {"n": 0}


def test_bootstrap_reamostra_eventos():
    linhas = [_linha("forte", ev=f"e{i}") for i in range(6)] + [_linha("seco", ev=f"e{i}") for i in range(6)]
    preds = [3] * 6 + [0] * 3 + [3] * 3
    b = bootstrap_eventos(linhas, _probs(preds), C, n=200, seed=1)
    lo, hi = b["f1_macro"]["ic95"]
    assert 0 <= lo <= b["f1_macro"]["media"] <= hi <= 1
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `ml/.venv/bin/python -m pytest -q ml/tests/test_metricas_fixa.py`
Expected: FAIL (`ModuleNotFoundError: cityrain_ml.evaluation.fixa`).

- [ ] **Step 3: Implementar**

Em `metricas.py` (depois de `spearman`):

```python
def kappa_quadratico(y_true: Sequence[int], y_pred: Sequence[int], n_classes: int) -> float:
    """Kappa de Cohen com peso quadrático: erra garoa por forte custa mais que por moderada."""
    y_true, y_pred = np.asarray(y_true, dtype=np.int64), np.asarray(y_pred, dtype=np.int64)
    if y_true.size == 0 or np.unique(y_true).size < 2:
        return float("nan")
    o = matriz_confusao(y_true, y_pred, n_classes).astype(np.float64)
    i, j = np.indices((n_classes, n_classes))
    w = (i - j) ** 2 / (n_classes - 1) ** 2
    e = np.outer(o.sum(1), o.sum(0)) / o.sum()
    return float(1 - (w * o).sum() / (w * e).sum())


def acuracia_chuva_vs_seco(y_true: Sequence[int], y_pred: Sequence[int], idx_seco: int = 0) -> float:
    """Acerto da pergunta 'está chovendo?' ignorando a intensidade."""
    t = np.asarray(y_true) != idx_seco
    p = np.asarray(y_pred) != idx_seco
    return float((t == p).mean()) if t.size else float("nan")


def recall_classe(m: np.ndarray, k: int) -> float | None:
    """Recall da classe k; None quando ela não aparece na verdade."""
    total = m[k].sum()
    return None if total == 0 else float(m[k, k] / total)
```

`ml/src/cityrain_ml/evaluation/fixa.py`:

```python
"""Métricas do modelo de câmera fixa por partição, câmera e período (NumPy puro)."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from cityrain_ml.evaluation.metricas import (
    acuracia_chuva_vs_seco,
    kappa_quadratico,
    matriz_confusao,
    recall_classe,
    resumo_classificacao,
    score_intensidade,
    spearman,
)


def _indices(linhas: list[dict], classes: Sequence[str]) -> list[int]:
    return [i for i, r in enumerate(linhas) if r["classe"] in classes]


def _recorte(linhas, probs, classes, chave) -> dict:
    grupos: dict[str, list[int]] = {}
    for i, r in enumerate(linhas):
        grupos.setdefault(r.get(chave) or "?", []).append(i)
    saida = {}
    for g, idx in sorted(grupos.items()):
        y = [classes.index(linhas[i]["classe"]) for i in idx]
        res = resumo_classificacao(y, probs[idx], classes)
        saida[g] = {"n": res["n"], "f1_macro": res["f1_macro"], "acuracia": res["acuracia"]}
    return saida


def metricas_particao(linhas: list[dict], probs: np.ndarray, classes: Sequence[str]) -> dict:
    classes = list(classes)
    idx = _indices(linhas, classes)
    if not idx:
        return {"n": 0}
    linhas = [linhas[i] for i in idx]
    probs = np.asarray(probs)[idx]
    y = [classes.index(r["classe"]) for r in linhas]
    pred = probs.argmax(1)
    m = matriz_confusao(y, pred, len(classes))
    mm = [float(r["mm_h"]) if r.get("mm_h") not in (None, "") else np.nan for r in linhas]
    ok = [i for i, v in enumerate(mm) if not np.isnan(v)]
    sc = score_intensidade(probs)
    return {
        "n": len(y),
        "resumo": resumo_classificacao(y, probs, classes),
        "qwk": kappa_quadratico(y, pred, len(classes)),
        "acuracia_chuva_vs_seco": acuracia_chuva_vs_seco(y, pred, classes.index("seco")) if "seco" in classes else None,
        "recall_forte": recall_classe(m, classes.index("forte")) if "forte" in classes else None,
        "spearman_score_mm_h": spearman([sc[i] for i in ok], [mm[i] for i in ok]) if len(ok) > 2 else None,
        "por_periodo": _recorte(linhas, probs, classes, "periodo"),
        "por_camera": _recorte(linhas, probs, classes, "camera"),
    }


def bootstrap_eventos(linhas: list[dict], probs: np.ndarray, classes: Sequence[str], n: int = 1000, seed: int = 0) -> dict:
    """IC 95% reamostrando eventos inteiros (a unidade estatística do projeto)."""
    classes = list(classes)
    idx = _indices(linhas, classes)
    linhas = [linhas[i] for i in idx]
    probs = np.asarray(probs)[idx]
    por_ev: dict[str, list[int]] = {}
    for i, r in enumerate(linhas):
        por_ev.setdefault(r["evento_id"], []).append(i)
    eventos = sorted(por_ev)
    rng = np.random.default_rng(seed)
    f1s, recs = [], []
    for _ in range(n):
        amostra = rng.choice(len(eventos), size=len(eventos), replace=True)
        ii = [i for e in amostra for i in por_ev[eventos[e]]]
        y = [classes.index(linhas[i]["classe"]) for i in ii]
        m = matriz_confusao(y, probs[ii].argmax(1), len(classes))
        f1s.append(resumo_classificacao(y, probs[ii], classes)["f1_macro"])
        r = recall_classe(m, classes.index("forte")) if "forte" in classes else None
        if r is not None:
            recs.append(r)

    def _ic(v):
        return {"media": float(np.mean(v)), "ic95": [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]} if v else None

    return {"n_eventos": len(eventos), "f1_macro": _ic(f1s), "recall_forte": _ic(recs)}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `ml/.venv/bin/python -m pytest -q ml/tests/test_metricas_fixa.py ml/tests/test_treino_metricas.py`
Expected: todos passam.

- [ ] **Step 5: Commit**

```bash
git add ml/src/cityrain_ml/evaluation ml/tests/test_metricas_fixa.py
git commit -m "feat(avaliacao): métricas do modelo fixo (QWK, chuva x seco, recortes, bootstrap por evento)"
```

---

### Task 2: Entrada de 6 canais na fábrica de modelos

**Files:**
- Modify: `ml/src/cityrain_ml/models/fabrica.py`
- Test: `ml/tests/test_fabrica_canais.py`

**Interfaces:**
- Produces: `construir(arquitetura: str, n_classes: int, pretreinado: bool = True, canais_entrada: int = 3) -> nn.Module`. Com 6 canais, a primeira convolução recebe os pesos ImageNet nos 3 primeiros canais e **zero** nos 3 da referência: o modelo começa idêntico ao de 3 canais e aprende a usar a referência.

- [ ] **Step 1: Testes que falham** (`ml/tests/test_fabrica_canais.py`)

```python
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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `ml/.venv/bin/python -m pytest -q ml/tests/test_fabrica_canais.py`
Expected: FAIL (`TypeError: construir() got an unexpected keyword argument 'canais_entrada'`).

- [ ] **Step 3: Implementar** (em `fabrica.py`)

```python
import torch


def _trocar_entrada(m: nn.Module, canais: int) -> None:
    """Primeira conv com `canais` entradas: pesos originais nos 3 primeiros, zero no resto."""
    if hasattr(m, "conv1"):
        velha, colocar = m.conv1, lambda nova: setattr(m, "conv1", nova)
    else:
        velha = m.features[0][0]

        def colocar(nova):
            m.features[0][0] = nova
    nova = nn.Conv2d(canais, velha.out_channels, velha.kernel_size, velha.stride, velha.padding,
                     dilation=velha.dilation, groups=velha.groups, bias=velha.bias is not None)
    with torch.no_grad():
        nova.weight.zero_()
        nova.weight[:, :3] = velha.weight
        if velha.bias is not None:
            nova.bias.copy_(velha.bias)
    colocar(nova)


def construir(arquitetura: str, n_classes: int, pretreinado: bool = True, canais_entrada: int = 3) -> nn.Module:
    if arquitetura not in _CONSTRUTORES:
        raise ValueError(f"arquitetura desconhecida: {arquitetura!r} (opções: {sorted(_CONSTRUTORES)})")
    if canais_entrada not in (3, 6):
        raise ValueError(f"canais_entrada deve ser 3 ou 6, não {canais_entrada}")
    m, cabeca = _CONSTRUTORES[arquitetura](pretreinado)
    cabeca(m, n_classes)
    if canais_entrada == 6:
        _trocar_entrada(m, 6)
    return m
```

Atualizar a docstring do módulo: "Com `canais_entrada=6` a entrada é imagem + referência seca (modelo de câmera fixa, variante F3)".

- [ ] **Step 4: Rodar e ver passar**

Run: `ml/.venv/bin/python -m pytest -q ml/tests/test_fabrica_canais.py`
Expected: todos passam.

- [ ] **Step 5: Commit**

```bash
git add ml/src/cityrain_ml/models/fabrica.py ml/tests/test_fabrica_canais.py
git commit -m "feat(modelos): entrada de 6 canais (imagem + referência seca) na fábrica"
```

---

### Task 3: Dataset e partições do modelo fixo (sem torch)

**Files:**
- Create: `ml/src/cityrain_ml/data/fixa.py`
- Test: `ml/tests/test_dataset_fixa.py`

**Interfaces:**
- Consumes: CSV do Plano B (colunas `caminho,classe,mm_h,particao,origem,evento_id,camera,periodo,ts_utc,referencia,metodo_rotulo`); `preparar`, `aumentar`, `ler_split` de `cityrain_ml.data.intensidade`.
- Produces:
  - `CLASSES_FIXA = ("seco", "garoa", "moderada", "forte")`.
  - `papeis_ircnn(cv: dict | None) -> dict[str, set[str] | None]` — igual a `eventos_ircnn` do treino v3 (`train`, `val`, `test`; `fold == "final"` → `test` vazio).
  - `subamostrar(linhas, maximo) -> list[dict]` — até `maximo` por `(evento_id, classe)`, igualmente espaçado na ordem `(ts_utc, número no nome do arquivo, caminho)`.
  - `particoes_fixa(linhas: list[dict], cfg: dict) -> tuple[dict[str, list[dict]], dict]` — devolve `{"train", "val", "test_ircnn", "test_camera", "test_prospectivo"}` e um dicionário de contagens (`descartadas_sem_referencia`). Regras:
    - `train` = linhas `train` + irCNN dos eventos de treino (subamostradas); `val` = linhas `val` + irCNN do evento de val (subamostradas); `test_ircnn` = irCNN dos eventos de teste (sem subamostrar).
    - Só linhas com `classe` em `CLASSES_FIXA`.
    - Com `cfg["dados"]["com_referencia"]`, descarta linhas com `referencia` vazia (contando).
    - Erro (`ValueError`) se alguma linha `train`/`val` for da câmera que aparece em `test_camera`.
  - `DatasetFixa(linhas, raiz, classes, altura, largura, aumentacao=None, seed=0, com_referencia=False)`, `__getitem__ -> (np.ndarray C×H×W float32, int)`, `rotulo(i) -> int`, atributo `epoca`.
  - `preparar_par(img, ref, altura, largura) -> np.ndarray 6×H×W`.

- [ ] **Step 1: Testes que falham** (`ml/tests/test_dataset_fixa.py`)

```python
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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `ml/.venv/bin/python -m pytest -q ml/tests/test_dataset_fixa.py`
Expected: FAIL (`ModuleNotFoundError: cityrain_ml.data.fixa`).

- [ ] **Step 3: Implementar `ml/src/cityrain_ml/data/fixa.py`**

```python
"""Dataset e partições do modelo de câmera fixa (spec CF4/CF5), sem PyTorch.

Lê o CSV de ``ml/scripts/dataset/montar_splits_fixa.py``. O irCNN entra pela CV
por evento com os mesmos folds do v3; lives entram pelas partições do CSV.
Com ``com_referencia`` cada amostra tem 6 canais: o frame e um ``seco`` da
mesma câmera no mesmo período, aumentados com os MESMOS parâmetros.
"""

from __future__ import annotations

import random
import re
from pathlib import Path

import numpy as np
from PIL import Image

from cityrain_ml.data.intensidade import aumentar, preparar

CLASSES_FIXA: tuple[str, ...] = ("seco", "garoa", "moderada", "forte")
_NUM = re.compile(r"(\d+)")


def papeis_ircnn(cv: dict | None) -> dict[str, set[str] | None]:
    if not cv:
        return {"train": set(), "val": set(), "test": None}
    folds, k = cv["folds"], cv["fold"]
    todos = {e for f in folds for e in f}
    if k == "final":
        val = {folds[0][0]}
        return {"train": todos - val, "val": val, "test": set()}
    test, val = set(folds[k]), {folds[(k + 1) % len(folds)][0]}
    return {"train": todos - test - val, "val": val, "test": test}


def _ordem(r: dict) -> tuple:
    m = _NUM.findall(Path(r["caminho"]).stem)
    return (r.get("ts_utc", ""), int(m[-1]) if m else 0, r["caminho"])


def subamostrar(linhas: list[dict], maximo: int) -> list[dict]:
    grupos: dict[tuple[str, str], list[dict]] = {}
    for r in linhas:
        grupos.setdefault((r["evento_id"], r["classe"]), []).append(r)
    saida = []
    for chave in sorted(grupos):
        rs = sorted(grupos[chave], key=_ordem)
        if len(rs) > maximo:
            idx = np.linspace(0, len(rs) - 1, maximo).round().astype(int)
            rs = [rs[i] for i in idx]
        saida.extend(rs)
    return saida


def particoes_fixa(linhas: list[dict], cfg: dict) -> tuple[dict[str, list[dict]], dict]:
    dados = cfg["dados"]
    linhas = [r for r in linhas if r["classe"] in CLASSES_FIXA]
    descartadas = 0
    if dados.get("com_referencia"):
        antes = len(linhas)
        linhas = [r for r in linhas if r.get("referencia")]
        descartadas = antes - len(linhas)
    por = lambda p: [r for r in linhas if r["particao"] == p]  # noqa: E731
    cv = dados.get("ircnn_cv")
    papeis = papeis_ircnn(cv)
    maximo = (cv or {}).get("max_por_evento", 200)
    ir = por("ircnn")
    parts = {
        "train": por("train") + subamostrar([r for r in ir if r["evento_id"] in papeis["train"]], maximo),
        "val": por("val") + subamostrar([r for r in ir if r["evento_id"] in papeis["val"]], maximo),
        "test_ircnn": ir if papeis["test"] is None else [r for r in ir if r["evento_id"] in papeis["test"]],
        "test_camera": por("test_camera"),
        "test_prospectivo": por("test_prospectivo"),
    }
    cams_teste = {r["camera"] for r in parts["test_camera"]}
    vazou = cams_teste & {r["camera"] for r in parts["train"] + parts["val"]}
    if vazou:
        raise ValueError(f"câmera de teste no treino/val: {sorted(vazou)}")
    return parts, {"descartadas_sem_referencia": descartadas}


def preparar_par(img: Image.Image, ref: Image.Image, altura: int, largura: int) -> np.ndarray:
    return np.concatenate([preparar(img, altura, largura), preparar(ref, altura, largura)], axis=0)


class DatasetFixa:
    """Map-style, compatível com DataLoader, sem herdar de torch (testes sem PyTorch)."""

    def __init__(self, linhas: list[dict], raiz: Path, classes: tuple[str, ...], altura: int, largura: int,
                 aumentacao: dict | None = None, seed: int = 0, com_referencia: bool = False) -> None:
        self.linhas, self.raiz = linhas, Path(raiz)
        self.indice = {c: i for i, c in enumerate(classes)}
        self.altura, self.largura = altura, largura
        self.aumentacao, self.seed, self.com_referencia = aumentacao, seed, com_referencia
        self.epoca = 0

    def __len__(self) -> int:
        return len(self.linhas)

    def rotulo(self, i: int) -> int:
        return self.indice.get(self.linhas[i]["classe"], -1)

    def __getitem__(self, i: int) -> tuple[np.ndarray, int]:
        r = self.linhas[i]
        img = Image.open(self.raiz / r["caminho"]).convert("RGB")
        ref = Image.open(self.raiz / r["referencia"]).convert("RGB") if self.com_referencia else None
        if self.aumentacao:
            semente = hash((self.seed, self.epoca, i))
            if ref is not None:
                # mesmo tamanho antes de aumentar => o mesmo recorte e o mesmo flip nos dois
                ref = aumentar(ref.resize(img.size, Image.BILINEAR), random.Random(semente), self.aumentacao)
            img = aumentar(img, random.Random(semente), self.aumentacao)
        if ref is not None:
            return preparar_par(img, ref, self.altura, self.largura), self.rotulo(i)
        return preparar(img, self.altura, self.largura), self.rotulo(i)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `ml/.venv/bin/python -m pytest -q ml/tests/test_dataset_fixa.py`
Expected: todos passam.

- [ ] **Step 5: Commit**

```bash
git add ml/src/cityrain_ml/data/fixa.py ml/tests/test_dataset_fixa.py
git commit -m "feat(dados): dataset e partições do modelo fixo com referência seca pareada"
```

---

### Task 4: Treino, avaliação e CV do modelo fixo

**Files:**
- Create: `ml/src/cityrain_ml/training/fixa.py`, `ml/scripts/treino/treinar_fixa.py`
- Create: `ml/configs/treino_fixa_f1_mnv3.yaml`, `ml/configs/treino_fixa_f2_effb0.yaml`, `ml/configs/treino_fixa_f3_mnv3_ref.yaml`
- Test: `ml/tests/test_treino_fixa.py`

**Interfaces:**
- Consumes: Tasks 1 a 3.
- Produces:
  - `treinar_fixa(cfg, raiz, saida) -> Path` (melhor checkpoint). Checkpoint: `{"estado", "epoca", "config", "classes": list(CLASSES_FIXA), "canais_entrada": 3|6}`.
  - `avaliar_fixa(ckpt, cfg, raiz, saida) -> dict` → `metricas.json` com `{"checkpoint_epoca", "ircnn_eventos", "particoes": {nome: metricas_particao(...)}}` e `predicoes_<particao>.csv` (`caminho,classe,mm_h,evento_id,camera,periodo,pred,p_seco,p_garoa,p_moderada,p_forte,score`).
  - `agregar_cv_fixa(runs: list[Path], saida: Path) -> dict` → `metricas_cv.json` com `test_ircnn_agregado` (metricas_particao sobre os 12 eventos), `bootstrap_ircnn` (bootstrap_eventos) e `test_camera`/`test_prospectivo` como média ± desvio entre folds de `resumo.f1_macro`, `qwk`, `acuracia_chuva_vs_seco`, `recall_forte`.
  - `executar_fixa(config_path, raiz, so_avaliar=None, fold=None) -> Path`.
  - CLI `ml/scripts/treino/treinar_fixa.py <config> [--cv | --fold k|final | --avaliar ckpt]`.
- Critério de seleção da época: média do F1 macro de `val` por domínio (`irCNN` × `live`), igual ao v3.

- [ ] **Step 1: Teste que falha** (`ml/tests/test_treino_fixa.py`) — treino minúsculo de ponta a ponta em CPU

```python
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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `ml/.venv/bin/python -m pytest -q ml/tests/test_treino_fixa.py`
Expected: FAIL (`ModuleNotFoundError: cityrain_ml.training.fixa`).

- [ ] **Step 3: Implementar `ml/src/cityrain_ml/training/fixa.py`**

```python
"""Treino e avaliação do modelo de câmera fixa (4 classes, só dado real; spec CF5).

Separado de ``training/intensidade.py`` de propósito: aquele gerou o v3 de
produção do carro e precisa continuar reproduzível. Mesmo desenho de CV por
evento do irCNN, mesma seleção de época (média do F1 por domínio no val).
"""

from __future__ import annotations

import csv
import json
import math
import random
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import yaml
from torch.utils.data import DataLoader

from cityrain_ml.data.fixa import CLASSES_FIXA, DatasetFixa, papeis_ircnn, particoes_fixa
from cityrain_ml.data.intensidade import ler_split
from cityrain_ml.evaluation.fixa import bootstrap_eventos, metricas_particao
from cityrain_ml.evaluation.metricas import resumo_classificacao, score_intensidade
from cityrain_ml.models.fabrica import construir

C = CLASSES_FIXA
TESTES = ("test_ircnn", "test_camera", "test_prospectivo")


def _disp(pedido: str) -> torch.device:
    if pedido != "auto":
        return torch.device(pedido)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _canais(cfg: dict) -> int:
    return 6 if cfg["dados"].get("com_referencia") else 3


def _ds(linhas, raiz, cfg, aumentar=False) -> DatasetFixa:
    h, w = cfg["entrada"]["altura"], cfg["entrada"]["largura"]
    return DatasetFixa(linhas, raiz, C, h, w, cfg.get("aumentacao") if aumentar else None, cfg["seed"],
                       com_referencia=bool(cfg["dados"].get("com_referencia")))


def _loader(ds, cfg, embaralhar) -> DataLoader:
    return DataLoader(ds, batch_size=cfg["treino"]["batch"], shuffle=embaralhar,
                      num_workers=cfg["treino"].get("workers", 4), persistent_workers=False)


@torch.no_grad()
def prever(modelo, ds, cfg, disp) -> np.ndarray:
    modelo.eval()
    saidas = [torch.softmax(modelo(x.to(disp)), 1).float().cpu().numpy() for x, _ in _loader(ds, cfg, False)]
    return np.concatenate(saidas) if saidas else np.zeros((0, len(C)))


def _pesos(linhas) -> torch.Tensor:
    cont = Counter(r["classe"] for r in linhas)
    n = sum(cont[c] for c in C)
    return torch.tensor([n / (len(C) * max(cont[c], 1)) for c in C], dtype=torch.float32)


def _f1_dominio(linhas, probs) -> dict[str, float]:
    grupos: dict[str, list[int]] = {}
    for i, r in enumerate(linhas):
        grupos.setdefault("irCNN" if r["origem"] == "irCNN" else "live", []).append(i)
    return {g: resumo_classificacao([C.index(linhas[i]["classe"]) for i in idx], probs[idx], C)["f1_macro"]
            for g, idx in sorted(grupos.items())}


def _particoes(cfg, raiz):
    return particoes_fixa(ler_split(raiz / cfg["dados"]["splits_csv"]), cfg)


def treinar_fixa(cfg: dict, raiz: Path, saida: Path) -> Path:
    random.seed(cfg["seed"])
    np.random.seed(cfg["seed"])
    torch.manual_seed(cfg["seed"])
    disp = _disp(cfg["treino"].get("dispositivo", "auto"))
    parts, info = _particoes(cfg, raiz)
    ds_tr, ds_va = _ds(parts["train"], raiz, cfg, aumentar=True), _ds(parts["val"], raiz, cfg)
    print(f"[fixa] {disp} | canais {_canais(cfg)} | train {Counter(r['classe'] for r in parts['train'])} | "
          f"val {Counter(r['classe'] for r in parts['val'])} | {info}")

    modelo = construir(cfg["modelo"]["arquitetura"], len(C), cfg["modelo"].get("pretreinado", True), _canais(cfg)).to(disp)
    perda = nn.CrossEntropyLoss(weight=_pesos(parts["train"]).to(disp), label_smoothing=cfg["treino"].get("label_smoothing", 0.0))
    otim = torch.optim.AdamW(modelo.parameters(), lr=cfg["treino"]["lr"], weight_decay=cfg["treino"].get("weight_decay", 1e-4))
    epocas = cfg["treino"]["epocas"]
    passos = epocas * math.ceil(len(ds_tr) / cfg["treino"]["batch"])
    sched = torch.optim.lr_scheduler.OneCycleLR(otim, max_lr=cfg["treino"]["lr"], total_steps=passos, pct_start=0.15)

    melhor, melhor_c, sem_melhora = saida / "melhor.pt", -1.0, 0
    historico = {"info": info, "epocas": []}
    for ep in range(epocas):
        t0 = time.time()
        ds_tr.epoca = ep
        modelo.train()
        soma, n = 0.0, 0
        for x, y in _loader(ds_tr, cfg, True):
            x, y = x.to(disp), y.to(disp)
            otim.zero_grad(set_to_none=True)
            loss = perda(modelo(x), y)
            loss.backward()
            otim.step()
            sched.step()
            soma, n = soma + loss.item() * y.size(0), n + y.size(0)
        p_va = prever(modelo, ds_va, cfg, disp)
        dom = _f1_dominio(parts["val"], p_va)
        criterio = float(np.mean(list(dom.values()))) if dom else 0.0
        historico["epocas"].append({"epoca": ep + 1, "loss": soma / max(n, 1), "val_f1_por_dominio": dom, "criterio": criterio, "s": round(time.time() - t0, 1)})
        print(f"[fixa] época {ep + 1}/{epocas} loss {soma / max(n, 1):.4f} | {dom} | critério {criterio:.4f}")
        estado = {"estado": modelo.state_dict(), "epoca": ep + 1, "config": cfg, "classes": list(C), "canais_entrada": _canais(cfg)}
        if cfg["treino"].get("sem_selecao_por_val"):
            torch.save(estado, melhor)
            continue
        if criterio > melhor_c:
            melhor_c, sem_melhora = criterio, 0
            torch.save(estado, melhor)
        else:
            sem_melhora += 1
            if sem_melhora >= cfg["treino"].get("paciencia", 5):
                break
    (saida / "historico.json").write_text(json.dumps(historico, indent=2, ensure_ascii=False))
    return melhor


def _gravar(path: Path, linhas, probs) -> None:
    sc = score_intensidade(probs) if len(linhas) else []
    with open(path, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["caminho", "classe", "mm_h", "evento_id", "camera", "periodo", "pred", *[f"p_{c}" for c in C], "score"])
        for r, p, s in zip(linhas, probs, sc):
            wr.writerow([r["caminho"], r["classe"], r["mm_h"], r["evento_id"], r["camera"], r["periodo"],
                         C[int(p.argmax())], *[f"{v:.4f}" for v in p], f"{s:.4f}"])


def avaliar_fixa(ckpt: Path, cfg: dict, raiz: Path, saida: Path) -> dict:
    disp = _disp(cfg["treino"].get("dispositivo", "auto"))
    estado = torch.load(ckpt, map_location="cpu", weights_only=False)
    modelo = construir(cfg["modelo"]["arquitetura"], len(C), pretreinado=False, canais_entrada=estado.get("canais_entrada", 3))
    modelo.load_state_dict(estado["estado"])
    modelo.to(disp)
    parts, _ = _particoes(cfg, raiz)
    met = {"checkpoint_epoca": estado["epoca"],
           "ircnn_eventos": {k: sorted(v) if v is not None else "todos" for k, v in papeis_ircnn(cfg["dados"].get("ircnn_cv")).items()},
           "particoes": {}}
    for p in ("val", *TESTES):
        probs = prever(modelo, _ds(parts[p], raiz, cfg), cfg, disp) if parts[p] else np.zeros((0, len(C)))
        _gravar(saida / f"predicoes_{p}.csv", parts[p], probs)
        met["particoes"][p] = metricas_particao(parts[p], probs, C)
    (saida / "metricas.json").write_text(json.dumps(met, indent=2, ensure_ascii=False, default=float))
    return met


def _ler_predicoes(path: Path) -> tuple[list[dict], np.ndarray]:
    with open(path, newline="") as f:
        linhas = list(csv.DictReader(f))
    return linhas, np.array([[float(r[f"p_{c}"]) for c in C] for r in linhas]).reshape(-1, len(C))


def agregar_cv_fixa(runs: list[Path], saida: Path) -> dict:
    linhas, probs, vistos = [], [], set()
    for run in runs:
        l, p = _ler_predicoes(run / "predicoes_test_ircnn.csv")
        evs = {r["evento_id"] for r in l}
        if evs & vistos:
            raise ValueError(f"evento testado em mais de um fold: {sorted(evs & vistos)}")
        vistos |= evs
        linhas += l
        probs.append(p)
    probs_np = np.concatenate(probs) if probs else np.zeros((0, len(C)))
    met = {"folds": [r.name for r in runs],
           "test_ircnn_agregado": metricas_particao(linhas, probs_np, C),
           "bootstrap_ircnn": bootstrap_eventos(linhas, probs_np, C) if linhas else None}
    por_fold = [json.loads((r / "metricas.json").read_text())["particoes"] for r in runs]
    for p in ("test_camera", "test_prospectivo"):
        met[p] = {}
        for chave in ("resumo.f1_macro", "qwk", "acuracia_chuva_vs_seco", "recall_forte"):
            vals = []
            for m in por_fold:
                if m[p].get("n", 0) == 0:
                    continue
                v = m[p]["resumo"]["f1_macro"] if chave == "resumo.f1_macro" else m[p][chave]
                if v is not None and not (isinstance(v, float) and math.isnan(v)):
                    vals.append(v)
            met[p][chave] = {"media": float(np.mean(vals)), "desvio": float(np.std(vals)), "valores": vals} if vals else None
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "metricas_cv.json").write_text(json.dumps(met, indent=2, ensure_ascii=False, default=float))
    return met


def executar_fixa(config_path: Path, raiz: Path, so_avaliar: Path | None = None, fold: int | str | None = None) -> Path:
    cfg = yaml.safe_load(Path(config_path).read_text())
    if fold is not None:
        cfg["dados"]["ircnn_cv"]["fold"] = fold
        cfg["nome"] = f"{cfg['nome']}_fold{fold}"
    if so_avaliar is not None:
        avaliar_fixa(so_avaliar, cfg, raiz, so_avaliar.parent)
        return so_avaliar.parent
    saida = raiz / "ml" / "runs" / f"{cfg['nome']}__{datetime.now():%Y%m%d_%H%M%S_%f}"
    saida.mkdir(parents=True, exist_ok=False)
    (saida / "config.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))
    avaliar_fixa(treinar_fixa(cfg, raiz, saida), cfg, raiz, saida)
    return saida
```

`ml/scripts/treino/treinar_fixa.py` segue `treinar_intensidade.py` (mesma CLI): importa `executar_fixa`, `agregar_cv_fixa`; com `--cv` roda `fold` = 0..n−1, depois `agregar_cv_fixa(runs, RAIZ / "ml/runs" / f"{cfg['nome']}__cv_<ts>")`; `_imprimir` mostra, por partição, `n`, `resumo.f1_macro`, `qwk`, `acuracia_chuva_vs_seco` e `recall_forte`.

Configs (todas com os mesmos `folds` do `treino_intensidade_cv_v3_mnv3.yaml`, `max_por_evento: 150`, `entrada` 288×384, `aumentacao` e `treino` iguais ao v3):
- `treino_fixa_f1_mnv3.yaml`: `nome: fixa_f1_mnv3`, `modelo.arquitetura: mobilenet_v3_large`, `dados.com_referencia: false`.
- `treino_fixa_f2_effb0.yaml`: `nome: fixa_f2_effb0`, `efficientnet_b0`, `com_referencia: false`, `treino.batch: 24`.
- `treino_fixa_f3_mnv3_ref.yaml`: `nome: fixa_f3_mnv3_ref`, `mobilenet_v3_large`, `com_referencia: true`.
Cada config começa com um comentário de 2 linhas dizendo o que testa e o comando de execução. `dados.splits_csv: ml/data/splits/fixa_v1.csv`.

- [ ] **Step 4: Rodar e ver passar**

Run: `ml/.venv/bin/python -m pytest -q ml/tests/test_treino_fixa.py`
Expected: `2 passed` (cerca de 1 a 2 min em CPU).

- [ ] **Step 5: Commit**

```bash
git add ml/src/cityrain_ml/training/fixa.py ml/scripts/treino/treinar_fixa.py ml/configs/treino_fixa_*.yaml ml/tests/test_treino_fixa.py
git commit -m "feat(treino): treino, avaliação e CV do modelo de câmera fixa (F1–F3)"
```

---

### Task 5: F0 — o v3 de produção nas câmeras fixas

**Files:**
- Create: `ml/scripts/avaliacao/avaliar_v3_em_fixa.py`
- Test: `ml/tests/test_f0_v3.py`

**Interfaces:**
- Produces: `metricas_v3_em_fixa(linhas: list[dict], probs3: np.ndarray) -> dict` — só linhas de chuva (`garoa`, `moderada`, `forte`), classes do v3; devolve `metricas_particao` com essas 3 classes. CLI `avaliar_v3_em_fixa.py --onnx backend/app/inference/modelos/intensidade.onnx --splits ml/data/splits/fixa_v1.csv --saida ml/resultados/fixa_f0_v3.json` avaliando `test_camera`, `test_prospectivo`, `train`+`val` (lives) e `ircnn`, com a nota `"ircnn": "visto no treino do v3 — não é teste"`.

- [ ] **Step 1: Teste que falha** (`ml/tests/test_f0_v3.py`)

```python
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
```

- [ ] **Step 2:** rodar e ver falhar. **Step 3:** implementar:

```python
#!/usr/bin/env python3
"""F0: o modelo v3 de produção (carro, 3 classes) aplicado às câmeras fixas.

Referência para mostrar quanto se ganha separando o domínio. O v3 não prevê
`seco` (no carro isso é do gate), então só os frames de chuva entram. O irCNN
foi usado no treino do v3: a linha dele é informativa, não é teste.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "ml" / "src"))
from cityrain_ml.data.intensidade import ler_split, preparar  # noqa: E402
from cityrain_ml.evaluation.fixa import metricas_particao  # noqa: E402

C3 = ("garoa", "moderada", "forte")


def metricas_v3_em_fixa(linhas: list[dict], probs3: np.ndarray) -> dict:
    idx = [i for i, r in enumerate(linhas) if r["classe"] in C3]
    return metricas_particao([linhas[i] for i in idx], np.asarray(probs3)[idx], C3)


def _prever(sess, linhas, lote=32) -> np.ndarray:
    from PIL import Image

    meta = sess.get_modelmeta().custom_metadata_map
    h, w = int(meta["altura"]), int(meta["largura"])
    nome = sess.get_inputs()[0].name
    saidas = []
    for i in range(0, len(linhas), lote):
        x = np.stack([preparar(Image.open(RAIZ / r["caminho"]), h, w) for r in linhas[i:i + lote]])
        lg = sess.run(None, {nome: x})[0]
        e = np.exp(lg - lg.max(1, keepdims=True))
        saidas.append(e / e.sum(1, keepdims=True))
    return np.concatenate(saidas) if saidas else np.zeros((0, 3))


def main() -> None:
    import onnxruntime as ort

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--onnx", type=Path, default=RAIZ / "backend/app/inference/modelos/intensidade.onnx")
    ap.add_argument("--splits", type=Path, default=RAIZ / "ml/data/splits/fixa_v1.csv")
    ap.add_argument("--saida", type=Path, default=RAIZ / "ml/resultados/fixa_f0_v3.json")
    args = ap.parse_args()
    sess = ort.InferenceSession(str(args.onnx), providers=["CPUExecutionProvider"])
    grupos = {"test_camera": {"test_camera"}, "test_prospectivo": {"test_prospectivo"}, "lives_treino_val": {"train", "val"}, "ircnn": {"ircnn"}}
    res = {"nota": {"ircnn": "visto no treino do v3 — não é teste"}}
    for nome, parts in grupos.items():
        linhas = [r for r in ler_split(args.splits, parts) if r["classe"] in C3]
        res[nome] = metricas_v3_em_fixa(linhas, _prever(sess, linhas)) if linhas else {"n": 0}
        print(nome, json.dumps({k: res[nome].get(k) for k in ("n", "qwk", "recall_forte")}, default=float))
    args.saida.write_text(json.dumps(res, indent=2, ensure_ascii=False, default=float))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4:** rodar e ver passar. **Step 5:** commit `feat(avaliacao): F0 — v3 de produção avaliado nas câmeras fixas`.

---

### Task 6: Exportar o modelo fixo e as referências para o backend

**Files:**
- Create: `ml/scripts/treino/exportar_onnx_fixa.py`
- Test: `ml/tests/test_exportar_fixa.py`

**Interfaces:**
- Consumes: checkpoint da Task 4 (`canais_entrada`, `classes`, `config`).
- Produces (contrato do Plano A Task 3):
  - ONNX com entrada `imagem` (1×C×H×W, lote dinâmico), saída `logits`, opset 17, metadata `classes` (JSON com `seco`), `altura`, `largura`, `media`, `desvio`, `arquitetura`, `experimento`, `checkpoint`, `epoca`, `saida`, `canais_entrada` (`"3"`/`"6"`), `referencia` (`"mesma_camera_mesmo_periodo"` ou `"nenhuma"`).
  - Com 6 canais: copia cada linha `particao == "referencia"` de câmera `live` para `<dir_refs>/fixa-<camera>/<periodo>.jpg`.
  - Funções: `exportar_fixa(ckpt: Path, destino: Path) -> dict`, `copiar_referencias(splits_csv: Path, raiz: Path, dir_refs: Path) -> list[Path]`, `conferir_paridade_fixa(info: dict, destino: Path, raiz: Path, n: int = 16) -> float`.
  - CLI: `exportar_onnx_fixa.py <ckpt> [--saida backend/app/inference/modelos/intensidade_fixa.onnx] [--referencias backend/app/inference/referencias]`; sai com erro se a paridade passar de 1e-4.

- [ ] **Step 1: Teste que falha** (`ml/tests/test_exportar_fixa.py`)

```python
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
```

- [ ] **Step 2:** rodar e ver falhar.
- [ ] **Step 3: Implementar** `exportar_onnx_fixa.py`, reaproveitando o padrão de `exportar_onnx.py` (mesma `torch.onnx.export(..., dynamo=False, opset_version=17)`, mesmos nomes `imagem`/`logits`, mesmo bloco de `metadata_props` + `onnx.checker`), com estas diferenças:
  - `torch.zeros(1, canais, h, w)` como exemplo de entrada, com `canais = estado.get("canais_entrada", 3)`;
  - `construir(..., canais_entrada=canais)`;
  - metadata extra `canais_entrada` e `referencia`;
  - `conferir_paridade_fixa` monta `DatasetFixa` (sem aumentação, `com_referencia = canais == 6`) com até `n` linhas das partições `test_camera`, `ircnn`, `val`, `train` (as que existirem, nessa ordem), compara softmax do PyTorch e do ORT e devolve o maior |Δp|;
  - `copiar_referencias` lê o CSV, filtra `particao == "referencia" and origem == "live"` e copia para `dir_refs / f"fixa-{camera}" / f"{periodo}.jpg"` (cria as pastas; devolve a lista em ordem);
  - `main` chama `copiar_referencias` só quando `canais == 6`, e imprime classes, canais, tamanho e paridade.
- [ ] **Step 4:** rodar e ver passar (`ml/.venv/bin/python -m pytest -q ml/tests/test_exportar_fixa.py`).
- [ ] **Step 5:** commit `feat(treino): exportador ONNX do modelo fixo com referências para o backend`.

---

### Task 7 [ORQUESTRADOR + HUMANO]: Rodar os experimentos e escolher

Não vai para subagente: é treino longo, com o Rodrigo presente, de dia.

- [ ] **Step 1 — Pré-requisito:** `ml/data/splits/fixa_v1.csv` gerado (Plano B Task 5) e sem `referencias_faltando`.
- [ ] **Step 2 — F0:** `ml/.venv/bin/python ml/scripts/avaliacao/avaliar_v3_em_fixa.py`.
- [ ] **Step 3 — F1, F2, F3**, um fold por job (~20 min cada no M-series):

```bash
for k in 0 1 2 3; do caffeinate -i ml/.venv/bin/python ml/scripts/treino/treinar_fixa.py ml/configs/treino_fixa_f1_mnv3.yaml --fold $k; done
# agregar os 4 runs mais recentes do F1:
ml/.venv/bin/python - <<'E'
import sys; from pathlib import Path
sys.path.insert(0, "ml/src")
from cityrain_ml.training.fixa import agregar_cv_fixa
runs = [sorted(Path("ml/runs").glob(f"fixa_f1_mnv3_fold{k}__*"))[-1] for k in range(4)]
print(agregar_cv_fixa(runs, Path("ml/runs/fixa_f1_mnv3__cv")))
E
```

Repetir para F2 e F3.
- [ ] **Step 4 — Escolha pelo critério fixado na spec (CF5):** maior F1 macro no irCNN agregado com IC; `recall_forte ≥ 0,7`; na `test_camera`, `acuracia_chuva_vs_seco ≥ 0,8` e Spearman > 0; empate estatístico → modelo menor. Registrar a decisão e os números numa tabela nova "Câmera fixa" em `docs/resultados-experimentos.md`, incluindo F0 e os IC.
- [ ] **Step 5 — Modelo final:** copiar a config vencedora para `treino_fixa_final.yaml` com `treino.epocas` = mediana das melhores épocas da CV e `treino.sem_selecao_por_val: true`; rodar `--fold final`; exportar:

```bash
ml/.venv/bin/python ml/scripts/treino/exportar_onnx_fixa.py ml/runs/<run_final>/melhor.pt
```

- [ ] **Step 6 — Grad-CAM** do vencedor por classe e por câmera (adaptar `ml/scripts/avaliacao/gradcam.py`, que usa `CLASSES` de 3 classes e 3 canais: passar `CLASSES_FIXA` e montar a entrada com `DatasetFixa`). Salvar em `ml/resultados/figuras/gradcam_fixa.jpg`.
- [ ] **Step 7 — Teste C (depois de 18/10):** `treinar_fixa.py <final> --avaliar ml/runs/<run_final>/melhor.pt` com o CSV recongelado; registrar o `test_prospectivo` sem retreinar.
- [ ] **Step 8 — Commit** do ONNX, das referências e dos resultados:

```bash
git add backend/app/inference/modelos/intensidade_fixa.onnx backend/app/inference/referencias ml/configs/treino_fixa_final.yaml ml/resultados docs/resultados-experimentos.md
git commit -m "feat(modelo): modelo de câmera fixa <F?> em produção"
```
