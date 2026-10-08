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


def mapa_referencia_trocada(linhas_split: list[dict]) -> dict[tuple[str, str], str]:
    """(câmera, período) -> câmera DIFERENTE cuja referência será usada na ablação de atalho.

    Rotação determinística sobre as câmeras que têm referência (ordem alfabética, começando
    na câmera seguinte): prefere uma câmera com referência do MESMO período; se nenhuma tiver,
    usa a primeira outra câmera com referência.
    """
    refs = [r for r in linhas_split if r["particao"] == "referencia"]
    por_cam: dict[str, dict[str, str]] = {}
    for r in refs:
        por_cam.setdefault(r["camera"], {})[r["periodo"]] = r["caminho"]
    cams = sorted(por_cam)
    mapa: dict[tuple[str, str], str] = {}
    for cam in sorted({r["camera"] for r in linhas_split} | set(cams)):
        candidatas = [c for c in cams if c > cam] + [c for c in cams if c < cam]
        if not candidatas:
            raise ValueError("a ablação de referência trocada precisa de referências de pelo menos 2 câmeras")
        for per in ("dia", "noite"):
            mesma = [c for c in candidatas if per in por_cam[c]]
            mapa[(cam, per)] = (mesma or candidatas)[0]
    return mapa


def _trocar_referencias(linhas: list[dict], linhas_split: list[dict]) -> list[dict]:
    """Cópia das linhas com ``referencia`` apontando para a de OUTRA câmera (mesmo período se houver)."""
    mapa = mapa_referencia_trocada(linhas_split)
    por_cam_per = {(r["camera"], r["periodo"]): r["caminho"] for r in linhas_split if r["particao"] == "referencia"}
    qualquer = {}
    for (cam, _), caminho in sorted(por_cam_per.items()):
        qualquer.setdefault(cam, caminho)
    saida = []
    for r in linhas:
        outra = mapa[(r["camera"], r["periodo"])]
        ref = por_cam_per.get((outra, r["periodo"])) or qualquer[outra]
        saida.append({**r, "referencia": ref})
    return saida


def avaliar_fixa(ckpt: Path, cfg: dict, raiz: Path, saida: Path, referencia_trocada: bool = False,
                 carimbo: str | None = None) -> dict:
    """Avalia um checkpoint em val e nos três testes.

    Papéis das partições (fold do irCNN, exigir_referencia, splits) vêm da config GRAVADA NO
    CHECKPOINT: avaliar com outra config não pode mudar quais eventos foram de teste. De ``cfg``
    só entram dispositivo, batch e workers. Sem ``carimbo`` grava ``metricas.json`` e
    ``predicoes_<partição>.csv`` (o run de treino); com ``carimbo`` grava
    ``metricas_avaliacao_<carimbo>.json`` e ``predicoes_avaliacao_<partição>_<carimbo>.csv`` sem tocar nos
    arquivos do run. ``referencia_trocada`` (só F3) dá a cada linha a referência de OUTRA câmera, o
    teste de que o modelo usa a referência como comparação e não como atalho de identificar a câmera;
    os arquivos ganham o sufixo ``_ref_trocada``.
    """
    estado = torch.load(ckpt, map_location="cpu", weights_only=False)
    cfg_ck = estado.get("config") or cfg
    cfg_av = {**cfg_ck, "treino": {**cfg_ck.get("treino", {}), **{k: v for k, v in cfg["treino"].items()
                                                                    if k in ("dispositivo", "batch", "workers")}}}
    canais = estado.get("canais_entrada", 3)
    if referencia_trocada and canais != 6:
        raise ValueError("referencia_trocada só faz sentido para modelo de 6 canais (F3)")
    disp = _disp(cfg_av["treino"].get("dispositivo", "auto"))
    modelo = construir(cfg_av["modelo"]["arquitetura"], len(C), pretreinado=False, canais_entrada=canais)
    modelo.load_state_dict(estado["estado"])
    modelo.to(disp)
    parts, info = _particoes(cfg_av, raiz)
    cv = cfg_av["dados"].get("ircnn_cv")
    met = {"checkpoint_epoca": estado["epoca"], "fold": (cv or {}).get("fold"), "papeis_da_config": "checkpoint",
           "ircnn_eventos": {k: sorted(v) if v is not None else "todos" for k, v in papeis_ircnn(cv).items()},
           "info_particoes": info, "referencia_trocada": referencia_trocada, "particoes": {}}
    if referencia_trocada:
        split = ler_split(raiz / cfg_av["dados"]["splits_csv"])
        parts = {p: _trocar_referencias(rs, split) for p, rs in parts.items()}
        mapa = mapa_referencia_trocada(split)
        met["referencia_trocada_mapa"] = {cam: outra for (cam, per), outra in sorted(mapa.items()) if per == "dia"}
    sufixo = ("_ref_trocada" if referencia_trocada else "")
    for p in ("val", *TESTES):
        probs = prever(modelo, _ds(parts[p], raiz, cfg_av), cfg_av, disp) if parts[p] else np.zeros((0, len(C)))
        nome = f"predicoes_avaliacao_{p}_{carimbo}{sufixo}.csv" if carimbo else f"predicoes_{p}{sufixo}.csv"
        _gravar(saida / nome, parts[p], probs)
        met["particoes"][p] = metricas_particao(parts[p], probs, C)
        if p in ("test_camera", "test_prospectivo") and met["particoes"][p].get("n", 0) > 0:
            met["particoes"][p]["bootstrap"] = bootstrap_eventos(parts[p], probs, C)
    nome_met = f"metricas_avaliacao_{carimbo}{sufixo}.json" if carimbo else f"metricas{sufixo}.json"
    (saida / nome_met).write_text(json.dumps(met, indent=2, ensure_ascii=False, default=float))
    return met


def _ler_predicoes(path: Path) -> tuple[list[dict], np.ndarray]:
    with open(path, newline="") as f:
        linhas = list(csv.DictReader(f))
    return linhas, np.array([[float(r[f"p_{c}"]) for c in C] for r in linhas]).reshape(-1, len(C))


def agregar_cv_fixa(runs: list[Path], saida: Path) -> dict:
    """Agrega os folds de uma CV. Falha se algum evento declarado na config não foi testado.

    O ``desvio`` entre folds é o desvio amostral (ddof=1); com um único fold fica ``None``.
    """
    cfg_run = yaml.safe_load((runs[0] / "config.yaml").read_text()) if runs and (runs[0] / "config.yaml").exists() else None
    if cfg_run is None or not (cfg_run["dados"].get("ircnn_cv") or {}).get("folds"):
        raise ValueError("sem config.yaml com dados.ircnn_cv.folds no primeiro run: não dá para checar a cobertura da CV")
    declarados = {e for f in cfg_run["dados"]["ircnn_cv"]["folds"] for e in f}
    linhas, probs, vistos = [], [], set()
    for run in runs:
        l, p = _ler_predicoes(run / "predicoes_test_ircnn.csv")
        evs = {r["evento_id"] for r in l}
        if evs & vistos:
            raise ValueError(f"evento testado em mais de um fold: {sorted(evs & vistos)}")
        vistos |= evs
        linhas += l
        probs.append(p)
    faltam = declarados - vistos
    if faltam:
        raise ValueError(f"CV incompleta: eventos declarados e nunca testados: {sorted(faltam)}")
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
            met[p][chave] = {"media": float(np.mean(vals)), "desvio": float(np.std(vals, ddof=1)) if len(vals) > 1 else None, "valores": vals} if vals else None
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "metricas_cv.json").write_text(json.dumps(met, indent=2, ensure_ascii=False, default=float))
    return met


def executar_fixa(config_path: Path, raiz: Path, so_avaliar: Path | None = None, fold: int | str | None = None,
                  referencia_trocada: bool = False) -> Path:
    cfg = yaml.safe_load(Path(config_path).read_text())
    if so_avaliar is not None:
        # papéis das partições vêm do checkpoint; resultados novos, com carimbo, sem sobrescrever o run
        avaliar_fixa(so_avaliar, cfg, raiz, so_avaliar.parent, referencia_trocada, f"{datetime.now():%Y%m%d_%H%M%S}")
        return so_avaliar.parent
    if referencia_trocada:
        raise ValueError("referencia_trocada só vale com so_avaliar")
    if fold is not None:
        cfg["dados"]["ircnn_cv"]["fold"] = fold
        cfg["nome"] = f"{cfg['nome']}_fold{fold}"
    saida = raiz / "ml" / "runs" / f"{cfg['nome']}__{datetime.now():%Y%m%d_%H%M%S_%f}"
    saida.mkdir(parents=True, exist_ok=False)
    (saida / "config.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))
    avaliar_fixa(treinar_fixa(cfg, raiz, saida), cfg, raiz, saida)
    return saida
