#!/usr/bin/env python3
"""Splits do modelo de câmera fixa (spec CF4): por evento e por câmera, só dado real.

Partições:
  train / val       lives das câmeras de treino (último evento de cada câmera = val)
  ircnn             todos os eventos do irCNN; a CV por evento é feita no treino
  test_camera       a câmera de teste inteira, nunca vista no treino (Teste B)
  test_prospectivo  frames a partir do congelamento (Teste C)
  referencia        um `seco` por (câmera, período) usado como referência seca

Uso:
    ml/.venv/bin/python ml/scripts/dataset/montar_splits_fixa.py --config ml/configs/splits_fixa_v1.yaml
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from paineis_revisao_fixa import ler_exclusoes  # noqa: E402

COLUNAS = ["caminho", "classe", "mm_h", "particao", "origem", "evento_id", "camera", "periodo", "ts_utc", "referencia", "metodo_rotulo"]


def _ts(r: dict) -> datetime | None:
    """Converte timestamp ISO para datetime ou None."""
    return datetime.fromisoformat(r["ts_utc"].replace("Z", "+00:00")) if r.get("ts_utc") else None


def _ler(path: Path) -> list[dict]:
    """Lê CSV e retorna lista de dicts."""
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def carregar_lives(manifest: Path, raiz_frames_rel: str, metodo_padrao: str = "") -> list[dict]:
    """Carrega linhas do manifest de lives com rótulo de classe.

    Args:
        manifest: caminho ao manifest CSV das lives
        raiz_frames_rel: prefixo relativo ao repo para caminhos de frames
        metodo_padrao: método de rótulo padrão se não informado no manifest

    Returns:
        Lista de dicts com colunas da spec, mais _pasta e _arquivo para matching.
    """
    saida = []
    for r in _ler(manifest):
        if not r.get("classe"):
            continue
        saida.append({
            "caminho": f"{raiz_frames_rel}/{r['pasta']}/{r['arquivo']}", "classe": r["classe"], "mm_h": r.get("mm_h", ""),
            "particao": "", "origem": "live", "evento_id": r["evento_id"], "camera": r["pasta"],
            "periodo": r.get("periodo", ""), "ts_utc": r.get("ts_utc", ""), "referencia": "",
            "metodo_rotulo": r.get("metodo_rotulo") or metodo_padrao, "_pasta": r["pasta"], "_arquivo": r["arquivo"],
        })
    return saida


def acrescentar_5km(lives: list[dict], linhas_5km: list[dict], classes: set[str]) -> list[dict]:
    """Acrescenta frames da regra a 5 km que não têm rótulo na regra estrita.

    Args:
        lives: linhas de lives rotuladas (com rótulo estrito)
        linhas_5km: frames da regra a 5 km
        classes: conjunto de classes a aceitar (ex: {"moderada", "forte"})

    Returns:
        Lista original mais extras com metodo_rotulo="raio_5km".
    """
    ja = {(r["_pasta"], r["_arquivo"]) for r in lives}
    extras = [dict(r, metodo_rotulo="raio_5km") for r in linhas_5km
              if r["classe"] in classes and (r["_pasta"], r["_arquivo"]) not in ja]
    return lives + extras


def _revisados(revisao_csv: Path | None, nome_manifest: str) -> set[tuple[str, str]]:
    """Pares (câmera, classe) que têm linhas no revisao.csv vindas do manifest `nome_manifest`."""
    if not revisao_csv or not Path(revisao_csv).is_file():
        return set()
    return {(r.get("camera") or r["pasta"], r["classe"]) for r in _ler(Path(revisao_csv))
            if r.get("manifest") == nome_manifest}


def carregar_ircnn(manifest: Path, prefixo: str) -> list[dict]:
    """Carrega eventos do irCNN com caminho prefixado.

    Args:
        manifest: CSV do irCNN
        prefixo: prefixo a adicionar aos caminhos (ex: "ml/")

    Returns:
        Lista de dicts com partição pré-definida como "ircnn".
    """
    return [{
        "caminho": f"{prefixo}{r['caminho']}", "classe": r["classe"], "mm_h": r.get("mm_h", ""), "particao": "ircnn",
        "origem": "irCNN", "evento_id": r["evento_id"], "camera": "ircnn", "periodo": r.get("periodo", ""),
        "ts_utc": "", "referencia": "", "metodo_rotulo": "pluviometro_local", "_pasta": "ircnn", "_arquivo": r["caminho"],
    } for r in _ler(manifest) if r.get("classe")]


def escolher_referencias(linhas: list[dict], congelamento: datetime) -> dict[tuple[str, str], dict]:
    """Escolhe um frame `seco` mediano por (câmera, período) como referência seca.

    Nas lives, só frames antes do congelamento. No irCNN, qualquer frame seco.

    Args:
        linhas: lista de todas as linhas (lives + irCNN)
        congelamento: timestamp de congelamento para prospectivo

    Returns:
        Dict {(câmera, período): frame_seco_mediano}.
    """
    grupos: dict[tuple[str, str], list[dict]] = {}
    for r in linhas:
        if r["classe"] != "seco":
            continue
        if r["origem"] == "live" and (_ts(r) is None or _ts(r) >= congelamento):
            continue
        grupos.setdefault((r["camera"], r["periodo"]), []).append(r)
    refs = {}
    for chave, rs in grupos.items():
        rs = sorted(rs, key=lambda r: (r["ts_utc"], r["caminho"]))
        refs[chave] = rs[len(rs) // 2]
    return refs


def atribuir_particoes(linhas: list[dict], camera_teste: str, congelamento: datetime) -> None:
    """Atribui partições em-place: test_camera, test_prospectivo, train ou val.

    Câmera de teste inteira vai para test_camera.
    Frames após congelamento vão para test_prospectivo.
    Das câmeras de treino com 2+ eventos, o último evento = val; outros = train.
    Câmeras com 1 evento = train.

    Args:
        linhas: lista de linhas a modificar em-place
        camera_teste: ID da câmera reservada para teste B
        congelamento: timestamp de congelamento
    """
    eventos_por_cam: dict[str, set[str]] = {}
    for r in linhas:
        if r["particao"]:
            continue
        if r["camera"] == camera_teste:
            r["particao"] = "test_camera"
        elif _ts(r) is not None and _ts(r) >= congelamento:
            r["particao"] = "test_prospectivo"
        else:
            eventos_por_cam.setdefault(r["camera"], set()).add(r["evento_id"])
    ultimo = {cam: max(evs) for cam, evs in eventos_por_cam.items() if len(evs) >= 2}
    for r in linhas:
        if not r["particao"]:
            r["particao"] = "val" if ultimo.get(r["camera"]) == r["evento_id"] else "train"


def limitar_por_evento_classe(linhas: list[dict], maximo: int) -> list[dict]:
    """Limita frames de train por (evento, classe) a um máximo, mantendo val e test inteiros.

    Args:
        linhas: lista de linhas
        maximo: máximo de frames por (evento, classe) em train

    Returns:
        Lista filtrada.
    """
    grupos: dict[tuple[str, str], list[dict]] = {}
    resto = []
    for r in linhas:
        (grupos.setdefault((r["evento_id"], r["classe"]), []) if r["particao"] == "train" else resto).append(r)
    saida = list(resto)
    for chave in sorted(grupos):
        rs = sorted(grupos[chave], key=lambda r: (r["ts_utc"], r["caminho"]))
        if len(rs) > maximo:
            idx = np.linspace(0, len(rs) - 1, maximo).round().astype(int)
            rs = [rs[i] for i in idx]
        saida.extend(rs)
    return saida


def montar(cfg: dict, raiz: Path) -> tuple[list[dict], dict]:
    """Monta splits completos: carrega, filtra, atribui partições, escolhe referências.

    Args:
        cfg: dicionário de configuração
        raiz: caminho raiz do repo (para resolver caminhos relativos)

    Returns:
        Tuple (linhas, resumo).
    """
    congelamento = datetime.fromisoformat(cfg["congelamento_utc"].replace("Z", "+00:00"))
    excluidos = Counter()

    lives = carregar_lives(Path(cfg["manifest_lives"]), cfg["raiz_frames_lives"])
    if cfg.get("manifest_lives_5km"):
        man5 = Path(cfg["manifest_lives_5km"])
        if not man5.is_file():
            print(f"[splits] nota: manifest a 5 km ausente ({man5.name}); seguindo só com a regra estrita")
        else:
            l5 = carregar_lives(man5, cfg["raiz_frames_lives"])
            todas = acrescentar_5km(lives, l5, set(cfg.get("classes_5km", ["moderada", "forte"])))
            extras = todas[len(lives):]
            # rótulo a 5 km só entra depois de revisão visual: exige linhas do revisao.csv
            # deste manifest para o (câmera, classe)
            revisados = _revisados(Path(cfg["revisao_csv"]) if cfg.get("revisao_csv") else None, man5.name)
            aceitos = [r for r in extras if (r["camera"], r["classe"]) in revisados]
            excluidos["5km_sem_revisao"] = len(extras) - len(aceitos)
            if excluidos["5km_sem_revisao"]:
                print(f"[splits] nota: {excluidos['5km_sem_revisao']} frames a 5 km descartados por falta de revisão "
                      f"visual (revisao.csv sem linhas de {man5.name} para o par câmera/classe)")
            lives = lives + aceitos

    if cfg.get("exigir_posicao_verificada", True):
        fontes = yaml.safe_load(Path(cfg["coleta_fixa_config"]).read_text())["fontes"]
        ok = {f["id"] for f in fontes if f.get("posicao_verificada")}
        antes = len(lives)
        lives = [r for r in lives if r["camera"] in ok]
        excluidos["posicao_nao_verificada"] = antes - len(lives)

    exclusoes = ler_exclusoes(Path(cfg["revisao_csv"])) if cfg.get("revisao_csv") else set()
    antes = len(lives)
    lives = [r for r in lives if (r["_pasta"], r["_arquivo"]) not in exclusoes]
    excluidos["revisao"] = antes - len(lives)

    linhas = lives + carregar_ircnn(Path(cfg["manifest_ircnn"]), cfg.get("prefixo_ircnn", "ml/"))

    refs = escolher_referencias(linhas, congelamento)
    ids_ref = {id(r) for r in refs.values()}
    for r in refs.values():
        r["particao"] = "referencia"
    faltando = set()
    for r in linhas:
        if id(r) in ids_ref:
            continue
        outro = "noite" if r["periodo"] == "dia" else "dia"
        ref = refs.get((r["camera"], r["periodo"])) or refs.get((r["camera"], outro))
        r["referencia"] = ref["caminho"] if ref else ""
        if not ref:
            faltando.add(r["camera"])

    atribuir_particoes(linhas, cfg["camera_teste"], congelamento)
    linhas = limitar_por_evento_classe(linhas, int(cfg.get("max_por_evento_classe", 200)))
    linhas.sort(key=lambda r: (r["particao"], r["camera"], r["ts_utc"], r["caminho"]))

    resumo = {
        "por_particao_classe": {p: dict(Counter(r["classe"] for r in linhas if r["particao"] == p))
                                for p in sorted({r["particao"] for r in linhas})},
        "por_camera": {c: dict(Counter(r["particao"] for r in linhas if r["camera"] == c))
                       for c in sorted({r["camera"] for r in linhas})},
        "eventos_por_particao": {p: len({r["evento_id"] for r in linhas if r["particao"] == p})
                                 for p in sorted({r["particao"] for r in linhas})},
        "por_metodo_rotulo": dict(Counter(r["metodo_rotulo"] for r in linhas)),
        "excluidos": dict(excluidos),
        "referencias_faltando": sorted(faltando),
        "congelamento_utc": cfg["congelamento_utc"],
    }
    return linhas, resumo


def escrever(linhas: list[dict], path: Path) -> None:
    """Escreve CSV com colunas exatas da spec.

    Args:
        linhas: lista de dicts
        path: caminho de saída
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=COLUNAS, extrasaction="ignore")
        wr.writeheader()
        wr.writerows(linhas)


def main() -> None:
    """Ponto de entrada: carrega config, monta splits, escreve CSV e resumo."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=RAIZ / "ml/configs/splits_fixa_v1.yaml")
    args = ap.parse_args()
    cfg = yaml.safe_load(args.config.read_text())
    cfg = {k: (str(RAIZ / v) if k.startswith(("manifest_", "coleta_fixa_config", "revisao_csv")) and v else v) for k, v in cfg.items()}
    linhas, resumo = montar(cfg, RAIZ)
    escrever(linhas, RAIZ / cfg["saida"])
    (RAIZ / cfg["resumo"]).write_text(json.dumps(resumo, indent=2, ensure_ascii=False))
    print(json.dumps(resumo, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
