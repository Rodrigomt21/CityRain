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
