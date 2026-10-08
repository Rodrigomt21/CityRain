"""Métricas do modelo de intensidade (contrato de saída da spec do dataset balanceado).

O que o treino precisa reportar (``docs/specs/spec-dataset-balanceado.md``):

- **F1 macro e matriz de confusão** em ``test_real`` e ``test_ircnn``.
- **Taxa de ordenação**: fração de pares em que o modelo dá intensidade maior ao
  frame que deveria ter mais chuva (YouTube ``pico`` > ``inicio``, 23/09 > garoa de
  13/09, YouTube forte > garoa). É a única métrica possível onde só há rótulo
  ordinal, e não classe.

A "intensidade" de um frame é a classe esperada sob o softmax,
``score = Σ p_k · k`` com ``k = 0, 1, 2`` para garoa, moderada, forte: contínua,
então ordena mesmo quando o argmax empata.

Tudo aqui é NumPy puro, para os testes não dependerem de PyTorch.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

CLASSES: tuple[str, ...] = ("garoa", "moderada", "forte")


def score_intensidade(probs: np.ndarray) -> np.ndarray:
    """Classe esperada ``Σ p_k·k`` por linha de ``probs`` (N×K)."""
    probs = np.asarray(probs, dtype=np.float64)
    return probs @ np.arange(probs.shape[1], dtype=np.float64)


def matriz_confusao(y_true: Sequence[int], y_pred: Sequence[int], n_classes: int) -> np.ndarray:
    """Matriz K×K com linhas = verdade, colunas = predição."""
    m = np.zeros((n_classes, n_classes), dtype=np.int64)
    np.add.at(m, (np.asarray(y_true, dtype=np.int64), np.asarray(y_pred, dtype=np.int64)), 1)
    return m


def f1_por_classe(m: np.ndarray) -> np.ndarray:
    """F1 de cada classe a partir da matriz de confusão (0 quando indefinido)."""
    tp = np.diag(m).astype(np.float64)
    pred = m.sum(axis=0).astype(np.float64)
    real = m.sum(axis=1).astype(np.float64)
    denom = pred + real
    return np.divide(2 * tp, denom, out=np.zeros_like(tp), where=denom > 0)


def f1_macro(m: np.ndarray) -> float:
    """Média do F1 só sobre as classes presentes na verdade.

    Em ``test_real`` só existe garoa: incluir moderada/forte (F1 = 0 por
    definição) derrubaria a média sem medir nada.
    """
    presentes = m.sum(axis=1) > 0
    if not presentes.any():
        return float("nan")
    return float(f1_por_classe(m)[presentes].mean())


def taxa_ordenacao(scores_maior: Sequence[float], scores_menor: Sequence[float]) -> float:
    """P(score de um frame do grupo "maior" > score de um do grupo "menor").

    Empate conta meio. É a AUC de Mann–Whitney, calculada por ranks em
    O(n log n) para aguentar os ~16 mil frames do irCNN sem montar os pares.
    """
    a = np.asarray(scores_maior, dtype=np.float64)
    b = np.asarray(scores_menor, dtype=np.float64)
    if a.size == 0 or b.size == 0:
        return float("nan")
    todos = np.concatenate([a, b])
    ordem = np.argsort(todos, kind="mergesort")
    ranks = np.empty(todos.size, dtype=np.float64)
    ordenados = todos[ordem]
    # rank médio para empates
    i = 0
    while i < ordenados.size:
        j = i
        while j + 1 < ordenados.size and ordenados[j + 1] == ordenados[i]:
            j += 1
        ranks[ordem[i : j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    soma_a = ranks[: a.size].sum()
    u = soma_a - a.size * (a.size + 1) / 2.0
    return float(u / (a.size * b.size))


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    """Correlação de Spearman (ranks médios em empates)."""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if x.size < 2:
        return float("nan")

    def _ranks(v: np.ndarray) -> np.ndarray:
        ordem = np.argsort(v, kind="mergesort")
        r = np.empty(v.size, dtype=np.float64)
        r[ordem] = np.arange(v.size, dtype=np.float64)
        # média nos empates
        _, inv, cont = np.unique(v, return_inverse=True, return_counts=True)
        soma = np.bincount(inv, weights=r)
        return soma[inv] / cont[inv]

    rx, ry = _ranks(x), _ranks(y)
    if rx.std() == 0 or ry.std() == 0:
        return float("nan")
    return float(np.corrcoef(rx, ry)[0, 1])


def resumo_classificacao(y_true: Sequence[int], probs: np.ndarray, classes: Sequence[str] = CLASSES) -> dict:
    """F1 macro, F1 por classe, acurácia e matriz de confusão de uma partição."""
    probs = np.asarray(probs)
    y_true = np.asarray(y_true, dtype=np.int64)
    y_pred = probs.argmax(axis=1)
    m = matriz_confusao(y_true, y_pred, len(classes))
    f1 = f1_por_classe(m)
    return {
        "n": int(y_true.size),
        "acuracia": float((y_pred == y_true).mean()) if y_true.size else float("nan"),
        "f1_macro": f1_macro(m),
        "f1_por_classe": {c: float(f1[i]) for i, c in enumerate(classes) if m[i].sum() > 0},
        "matriz_confusao": {"classes": list(classes), "linhas_verdade": m.tolist()},
    }


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
