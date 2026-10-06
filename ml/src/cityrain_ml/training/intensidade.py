"""Treino e avaliação do modelo de intensidade (garoa | moderada | forte).

Fluxo de um experimento (1 YAML = 1 experimento):

1. treina em ``train`` e escolhe a época pelo F1 macro de ``val``. Os testes
   NUNCA guiam a escolha;
2. avalia o melhor checkpoint em todas as partições de teste do CSV;
3. grava ``config.yaml``, ``historico.json``, ``metricas.json`` e
   ``predicoes_<particao>.csv`` em ``ml/runs/<nome>__<timestamp>/``.

``seco`` não é classe deste modelo: na cascata ele sai do gate binário. Os 74
frames ``seco`` do irCNN ficam fora do F1 de 3 classes e entram só no Spearman.

Referência "sem sintético": o treino sem sintético tem uma classe só (garoa), e
o melhor que um modelo assim faz é responder garoa sempre. Essa linha é
calculada analiticamente (``baseline_constante``) no mesmo teste, em vez de
treinar um modelo degenerado.

Validação cruzada por evento no irCNN (``dados.ircnn_cv``): o irCNN é câmera
fixa sem para-brisa, então como teste puro ele só mede gap de domínio (v1: F1
0,07). Com ``ircnn_cv`` os 12 eventos são divididos em folds DECLARADOS no YAML;
no fold ``k`` os eventos de ``k`` são teste, o primeiro evento do fold ``k+1`` é
val e o resto entra no treino, subamostrado em ``max_por_evento`` frames
igualmente espaçados no tempo (frames vizinhos são quase iguais).
"""

from __future__ import annotations

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

from cityrain_ml.data.intensidade import DatasetIntensidade, ler_split
from cityrain_ml.evaluation.metricas import (
    CLASSES,
    resumo_classificacao,
    score_intensidade,
    spearman,
    taxa_ordenacao,
)
from cityrain_ml.models.fabrica import construir


def _dispositivo(pedido: str) -> torch.device:
    if pedido != "auto":
        return torch.device(pedido)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _fixar_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def _loader(ds: DatasetIntensidade, cfg: dict, embaralhar: bool) -> DataLoader:
    return DataLoader(
        ds,
        batch_size=cfg["treino"]["batch"],
        shuffle=embaralhar,
        num_workers=cfg["treino"].get("workers", 4),
        persistent_workers=False,  # re-spawn por época propaga ds.epoca à aumentação
    )


@torch.no_grad()
def prever(modelo: nn.Module, ds: DatasetIntensidade, cfg: dict, disp: torch.device) -> np.ndarray:
    """Probabilidades N×K na ordem das linhas do dataset."""
    modelo.eval()
    saidas = []
    for x, _ in _loader(ds, cfg, embaralhar=False):
        saidas.append(torch.softmax(modelo(x.to(disp)), dim=1).float().cpu().numpy())
    return np.concatenate(saidas) if saidas else np.zeros((0, len(CLASSES)))


def _pesos_classe(linhas: list[dict], classes: tuple[str, ...]) -> torch.Tensor:
    """Pesos inversos à frequência (contrato da spec: não descartar dado real)."""
    cont = Counter(r["classe"] for r in linhas)
    n = sum(cont[c] for c in classes)
    return torch.tensor([n / (len(classes) * max(cont[c], 1)) for c in classes], dtype=torch.float32)


def eventos_ircnn(cfg: dict) -> dict[str, set[str]]:
    """Papel de cada evento do irCNN no fold atual: ``train``, ``val`` e ``test``.

    Sem ``dados.ircnn_cv`` todo o irCNN é teste (desenho v1).
    """
    cv = cfg["dados"].get("ircnn_cv")
    if not cv:
        return {"train": set(), "val": set(), "test": None}  # None = todos
    folds, k = cv["folds"], cv["fold"]
    if k == "final":
        # modelo de produção: todos os eventos no treino, menos 1 de val para
        # escolher a época. Sem teste no irCNN — a nota dele é a média da CV.
        val = {folds[0][0]}
        return {"train": {e for f in folds for e in f} - val, "val": val, "test": set()}
    test = set(folds[k])
    val = {folds[(k + 1) % len(folds)][0]}
    train = {e for f in folds for e in f} - test - val
    return {"train": train, "val": val, "test": test}


def subamostrar_por_evento(linhas: list[dict], maximo: int, por_classe: bool = False) -> list[dict]:
    """Até ``maximo`` frames por evento, igualmente espaçados na ordem do caminho (tempo).

    Com ``por_classe`` o teto vale por (evento, classe): a garoa do irCNN (~3% dos
    frames, concentrada no começo/fim dos eventos) deixa de sumir na amostragem.
    Sem isso o modelo aprendeu "cara de irCNN => não é garoa" (CV v1: F1 garoa 0,02).
    """
    por_ev: dict[str, list[dict]] = {}
    for r in linhas:
        chave = f"{r['evento_id']}|{r['classe']}" if por_classe else r["evento_id"]
        por_ev.setdefault(chave, []).append(r)
    saida = []
    for ev in sorted(por_ev):
        rs = sorted(por_ev[ev], key=lambda r: _tempo_ircnn(r["caminho"]))
        if len(rs) > maximo:
            idx = np.linspace(0, len(rs) - 1, maximo).round().astype(int)
            rs = [rs[i] for i in idx]
        saida.extend(rs)
    return saida


def _tempo_ircnn(caminho: str) -> int:
    nome = Path(caminho).stem  # t1507
    return int(nome[1:]) if nome[1:].isdigit() else 0


def montar_particoes(cfg: dict, csv_path: Path) -> tuple[list[dict], list[dict]]:
    """Linhas de treino e val, incluindo eventos do irCNN quando há ``ircnn_cv``."""
    origens = set(cfg["dados"].get("origens_treino", ["real", "sintetico"]))
    lin_tr = [r for r in ler_split(csv_path, {"train"}) if r["origem"] in origens and r["classe"] in CLASSES]
    lin_va = [r for r in ler_split(csv_path, {"val"}) if r["classe"] in CLASSES]
    papeis = eventos_ircnn(cfg)
    if papeis["train"] or papeis["val"]:
        ir = [r for r in ler_split(csv_path, {"test_ircnn"}) if r["classe"] in CLASSES]
        maximo = cfg["dados"]["ircnn_cv"].get("max_por_evento", 200)
        por_classe = cfg["dados"]["ircnn_cv"].get("amostrar_por_classe", False)
        lin_tr += subamostrar_por_evento([r for r in ir if r["evento_id"] in papeis["train"]], maximo, por_classe)
        lin_va += subamostrar_por_evento([r for r in ir if r["evento_id"] in papeis["val"]], maximo, por_classe)
    return lin_tr, lin_va


def _f1_por_dominio(linhas: list[dict], probs: np.ndarray) -> dict[str, float]:
    """F1 macro do val separado em domínio próprio (real+sintético) e irCNN.

    A escolha do checkpoint usa a média dos domínios presentes: sem isso os ~1,5
    mil frames próprios do val abafam os ~200 do evento irCNN de val.
    """
    grupos: dict[str, list[int]] = {}
    for i, r in enumerate(linhas):
        grupos.setdefault("irCNN" if r["origem"] == "irCNN" else "proprio", []).append(i)
    return {
        g: resumo_classificacao([CLASSES.index(linhas[i]["classe"]) for i in idx], probs[idx])["f1_macro"]
        for g, idx in sorted(grupos.items(), reverse=True)
    }


def treinar(cfg: dict, raiz: Path, saida: Path) -> Path:
    """Treina e devolve o caminho do melhor checkpoint."""
    _fixar_seed(cfg["seed"])
    disp = _dispositivo(cfg["treino"].get("dispositivo", "auto"))
    csv_path = raiz / cfg["dados"]["splits_csv"]
    h, w = cfg["entrada"]["altura"], cfg["entrada"]["largura"]

    lin_tr, lin_va = montar_particoes(cfg, csv_path)
    ds_tr = DatasetIntensidade(lin_tr, raiz, CLASSES, h, w, cfg.get("aumentacao"), cfg["seed"])
    ds_va = DatasetIntensidade(lin_va, raiz, CLASSES, h, w)
    print(f"[treino] {disp} | train {Counter(r['classe'] for r in lin_tr)} | val {Counter(r['classe'] for r in lin_va)}")

    modelo = construir(cfg["modelo"]["arquitetura"], len(CLASSES), cfg["modelo"].get("pretreinado", True)).to(disp)
    perda = nn.CrossEntropyLoss(
        weight=_pesos_classe(lin_tr, CLASSES).to(disp),
        label_smoothing=cfg["treino"].get("label_smoothing", 0.0),
    )
    otim = torch.optim.AdamW(modelo.parameters(), lr=cfg["treino"]["lr"], weight_decay=cfg["treino"].get("weight_decay", 1e-4))
    epocas = cfg["treino"]["epocas"]
    passos = epocas * math.ceil(len(ds_tr) / cfg["treino"]["batch"])
    sched = torch.optim.lr_scheduler.OneCycleLR(otim, max_lr=cfg["treino"]["lr"], total_steps=passos, pct_start=0.15)

    melhor, melhor_f1, sem_melhora = saida / "melhor.pt", -1.0, 0
    paciencia = cfg["treino"].get("paciencia", 5)
    historico = []
    for ep in range(epocas):
        t0 = time.time()
        ds_tr.epoca = ep
        modelo.train()
        soma, n = 0.0, 0
        for x, y in _loader(ds_tr, cfg, embaralhar=True):
            x, y = x.to(disp), y.to(disp)
            otim.zero_grad(set_to_none=True)
            loss = perda(modelo(x), y)
            loss.backward()
            otim.step()
            sched.step()
            soma += loss.item() * y.size(0)
            n += y.size(0)
        p_va = prever(modelo, ds_va, cfg, disp)
        r_va = resumo_classificacao([ds_va.rotulo(i) for i in range(len(ds_va))], p_va)
        f1_dom = _f1_por_dominio(lin_va, p_va)
        criterio = float(np.mean(list(f1_dom.values())))
        historico.append({"epoca": ep + 1, "loss_treino": soma / n, "val_f1_macro": r_va["f1_macro"], "val_acuracia": r_va["acuracia"], "val_f1_por_dominio": f1_dom, "criterio": criterio, "s": round(time.time() - t0, 1)})
        doms = " ".join(f"{k} {v:.3f}" for k, v in f1_dom.items())
        print(f"[treino] época {ep + 1}/{epocas} loss {soma / n:.4f} | val F1 {r_va['f1_macro']:.4f} ({doms}) critério {criterio:.4f} | {time.time() - t0:.0f}s")
        if cfg["treino"].get("sem_selecao_por_val"):
            # modelo final: nº de épocas fixo (mediana da CV) e fica a ÚLTIMA. Com 1 só
            # evento irCNN no val, escolher a época por ele é ruído (final v3: oscilou
            # 0,37-0,76 e parou na época 4).
            torch.save({"estado": modelo.state_dict(), "epoca": ep + 1, "config": cfg, "classes": list(CLASSES)}, melhor)
            continue
        if criterio > melhor_f1:
            melhor_f1, sem_melhora = criterio, 0
            torch.save({"estado": modelo.state_dict(), "epoca": ep + 1, "config": cfg, "classes": list(CLASSES)}, melhor)
        else:
            sem_melhora += 1
            if sem_melhora >= paciencia:
                print(f"[treino] parada antecipada: {paciencia} épocas sem melhora no val")
                break
    (saida / "historico.json").write_text(json.dumps(historico, indent=2, ensure_ascii=False))
    return melhor


def _constante_garoa(y: list[int]) -> dict:
    probs = np.zeros((len(y), len(CLASSES)))
    probs[:, 0] = 1.0
    return resumo_classificacao(y, probs)


def avaliar(ckpt: Path, cfg: dict, raiz: Path, saida: Path) -> dict:
    """Avalia o checkpoint em todas as partições de teste e grava métricas + predições."""
    disp = _dispositivo(cfg["treino"].get("dispositivo", "auto"))
    estado = torch.load(ckpt, map_location="cpu", weights_only=False)
    modelo = construir(cfg["modelo"]["arquitetura"], len(CLASSES), pretreinado=False)
    modelo.load_state_dict(estado["estado"])
    modelo.to(disp)
    h, w = cfg["entrada"]["altura"], cfg["entrada"]["largura"]
    csv_path = raiz / cfg["dados"]["splits_csv"]

    particoes = ["val", "test_real", "test_ircnn", "test_ordinal_2309", "test_ordinal_youtube"]
    if ler_split(csv_path, {"test_lives"}):
        particoes.append("test_lives")  # câmera fixa separada, nunca vista no treino
    papeis = eventos_ircnn(cfg)
    probs: dict[str, np.ndarray] = {}
    linhas: dict[str, list[dict]] = {}
    for p in particoes:
        if p == "val":
            linhas[p] = montar_particoes(cfg, csv_path)[1]
        elif p == "test_ircnn" and papeis["test"] is not None:
            linhas[p] = [r for r in ler_split(csv_path, {p}) if r["evento_id"] in papeis["test"]]
        else:
            linhas[p] = ler_split(csv_path, {p})
        t0 = time.time()
        probs[p] = prever(modelo, DatasetIntensidade(linhas[p], raiz, CLASSES, h, w), cfg, disp)
        print(f"[avaliação] {p}: {len(linhas[p])} frames em {time.time() - t0:.0f}s")
        _gravar_predicoes(saida / f"predicoes_{p}.csv", linhas[p], probs[p])

    def classificados(p: str, filtro=lambda r: True) -> tuple[list[int], np.ndarray]:
        idx = [i for i, r in enumerate(linhas[p]) if r["classe"] in CLASSES and filtro(linhas[p][i])]
        return [CLASSES.index(linhas[p][i]["classe"]) for i in idx], probs[p][idx]

    sc = {p: score_intensidade(probs[p]) for p in particoes}
    met: dict = {
        "checkpoint_epoca": estado["epoca"],
        "ircnn_eventos": {k: sorted(v) if v is not None else "todos" for k, v in papeis.items()},
        "classificacao": {},
        "ordenacao": {},
        "baseline_constante_garoa": {},
    }
    for p in [q for q in ("val", "test_real", "test_ircnn", "test_lives") if q in particoes]:
        y, pr = classificados(p)
        met["classificacao"][p] = resumo_classificacao(y, pr)
        met["baseline_constante_garoa"][p] = _constante_garoa(y)
    for periodo in ["dia", "noite"]:
        y, pr = classificados("test_ircnn", lambda r, per=periodo: r["periodo"] == per)
        met["classificacao"][f"test_ircnn_{periodo}"] = resumo_classificacao(y, pr)
    # por evento: o irCNN tem 12 eventos e a média esconde se é um só que salva
    por_evento = {}
    for ev in sorted({r["evento_id"] for r in linhas["test_ircnn"]}):
        y, pr = classificados("test_ircnn", lambda r, e=ev: r["evento_id"] == e)
        por_evento[ev] = {k: v for k, v in resumo_classificacao(y, pr).items() if k in ("n", "acuracia", "f1_macro")}
    met["classificacao"]["test_ircnn_por_evento"] = por_evento

    yt = linhas["test_ordinal_youtube"]
    yt_pico = [sc["test_ordinal_youtube"][i] for i, r in enumerate(yt) if r["trecho"] == "pico"]
    yt_ini = [sc["test_ordinal_youtube"][i] for i, r in enumerate(yt) if r["trecho"] == "inicio"]
    met["ordenacao"] = {
        "youtube_pico_maior_que_inicio": taxa_ordenacao(yt_pico, yt_ini),
        "2309_maior_que_garoa_1309": taxa_ordenacao(sc["test_ordinal_2309"], sc["test_real"]),
        "youtube_maior_que_garoa_1309": taxa_ordenacao(sc["test_ordinal_youtube"], sc["test_real"]),
        "ircnn_spearman_score_vs_mm_h": spearman(sc["test_ircnn"], [float(r["mm_h"]) for r in linhas["test_ircnn"]]),
        "score_medio": {p: float(np.mean(sc[p])) for p in particoes},
    }
    (saida / "metricas.json").write_text(json.dumps(met, indent=2, ensure_ascii=False))
    return met


def agregar_cv(runs: list[Path], saida: Path) -> dict:
    """Junta as predições de irCNN de todos os folds (cada evento testado uma vez) e
    recalcula as métricas sobre os 12 eventos. Ordenação e test_real: média ± desvio
    entre folds, porque ali todos os folds avaliam os mesmos frames."""
    import csv

    linhas, probs, vistos = [], [], set()
    for run in runs:
        with open(run / "predicoes_test_ircnn.csv", newline="") as f:
            do_run = list(csv.DictReader(f))
        eventos = {r["evento_id"] for r in do_run}
        if eventos & vistos:
            raise ValueError(f"evento testado em mais de um fold: {sorted(eventos & vistos)}")
        vistos |= eventos
        linhas += do_run
        probs += [[float(r[f"p_{c}"]) for c in CLASSES] for r in do_run]
    probs_np = np.array(probs)
    idx = [i for i, r in enumerate(linhas) if r["classe"] in CLASSES]
    y = [CLASSES.index(linhas[i]["classe"]) for i in idx]
    met = {
        "folds": [str(r.name) for r in runs],
        "test_ircnn_agregado": resumo_classificacao(y, probs_np[idx]),
        "baseline_constante_garoa_ircnn": _constante_garoa(y),
        "ircnn_spearman_score_vs_mm_h": spearman(score_intensidade(probs_np), [float(r["mm_h"]) for r in linhas]),
    }
    por_fold = [json.loads((r / "metricas.json").read_text()) for r in runs]
    chaves = [("classificacao", "test_real", "f1_macro"), ("classificacao", "test_ircnn", "f1_macro")]
    chaves += [("ordenacao", k, None) for k in por_fold[0]["ordenacao"] if k != "score_medio"]
    met["por_fold"] = {}
    for a, b, c in chaves:
        vals = [m[a][b][c] if c else m[a][b] for m in por_fold]
        met["por_fold"][f"{b}.{c}" if c else b] = {"media": float(np.mean(vals)), "desvio": float(np.std(vals)), "valores": vals}
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "metricas_cv.json").write_text(json.dumps(met, indent=2, ensure_ascii=False))
    return met


def _gravar_predicoes(path: Path, linhas: list[dict], probs: np.ndarray) -> None:
    import csv

    with open(path, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["caminho", "classe", "mm_h", "evento_id", "pred", *[f"p_{c}" for c in CLASSES], "score"])
        sc = score_intensidade(probs)
        for r, p, s in zip(linhas, probs, sc):
            wr.writerow([r["caminho"], r["classe"], r["mm_h"], r["evento_id"], CLASSES[int(p.argmax())], *[f"{v:.4f}" for v in p], f"{s:.4f}"])


def executar(config_path: Path, raiz: Path, so_avaliar: Path | None = None, fold: int | str | None = None) -> Path:
    cfg = yaml.safe_load(Path(config_path).read_text())
    if fold is not None:
        cfg["dados"]["ircnn_cv"]["fold"] = fold
        cfg["nome"] = f"{cfg['nome']}_fold{fold}"
    if so_avaliar is not None:
        saida = so_avaliar.parent
        avaliar(so_avaliar, cfg, raiz, saida)
        return saida
    saida = raiz / "ml" / "runs" / f"{cfg['nome']}__{datetime.now():%Y%m%d_%H%M%S}"
    saida.mkdir(parents=True, exist_ok=False)
    (saida / "config.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))
    ckpt = treinar(cfg, raiz, saida)
    avaliar(ckpt, cfg, raiz, saida)
    return saida
