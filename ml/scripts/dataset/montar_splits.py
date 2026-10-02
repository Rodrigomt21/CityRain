#!/usr/bin/env python3
"""Monta os splits por sessão do dataset de intensidade e do gate (D3).

Partições vêm do YAML (``ml/configs/splits_intensidade.yaml``), nunca sorteadas.
Saídas: intensidade_v1.csv, gate_v1.csv e intensidade_v1_resumo.json.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

RAIZ = Path(__file__).resolve().parents[3]
COLUNAS = [
    "caminho", "classe", "mm_h", "particao", "origem", "evento_id",
    "base_frame", "seed", "rotulo_fraco", "trecho", "periodo",
]


def _ler_csv(caminho: Path) -> list[dict[str, str]]:
    with open(caminho, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _da_raiz(caminho: str) -> str:
    """Normaliza para caminho relativo à raiz do repo (manifests antigos usam ml/ como base)."""
    return caminho if caminho.startswith("ml/") else f"ml/{caminho}"


def _ts(linha: dict[str, str]) -> datetime:
    return datetime.fromisoformat(linha["ts_utc"].replace("Z", "+00:00")).astimezone(timezone.utc)


def _local(linha: dict[str, str], offset_h: float) -> datetime:
    return _ts(linha) + timedelta(hours=offset_h)


def _hms(texto: str):
    return datetime.strptime(texto, "%H:%M:%S").time()


def _stride(linhas: list[dict[str, str]], stride_s: float) -> list[dict[str, str]]:
    """Mantém 1 frame a cada ``stride_s`` segundos, por sessão, em ordem temporal."""
    mantidas: list[dict[str, str]] = []
    ultimo: dict[str, datetime] = {}
    for lin in sorted(linhas, key=lambda r: (r["evento_id"], _ts(r), r["arquivo"])):
        t = _ts(lin)
        ev = lin["evento_id"]
        if ev not in ultimo or (t - ultimo[ev]).total_seconds() >= stride_s:
            mantidas.append(lin)
            ultimo[ev] = t
    return mantidas


def _casa(regra: dict[str, Any], lin: dict[str, str], offset_h: float) -> bool:
    if lin["evento_id"] != regra["evento_id"] or lin["classe"] != regra["classe"]:
        return False
    if lin.get("motivo_exclusao"):
        return False
    hora = _local(lin, offset_h).time()
    if "local_ate" in regra and not hora < _hms(regra["local_ate"]):
        return False
    if "local_desde" in regra and not hora >= _hms(regra["local_desde"]):
        return False
    return True


def _selecionar(regra, imt, cfg):
    sel = [r for r in imt if _casa(regra, r, cfg["utc_offset_h"])]
    return _stride(sel, cfg["stride_s"]) if regra.get("stride") else sorted(
        sel, key=lambda r: (_ts(r), r["arquivo"])
    )


def _linha(lin, cfg, classe, particao, origem, **extra) -> dict[str, Any]:
    out = dict.fromkeys(COLUNAS, "")
    out.update(
        caminho=f"{cfg['imagens_dir']}/{lin['pasta']}/{lin['arquivo']}",
        classe=classe, mm_h=lin.get("mm_h", "") if classe else "",
        particao=particao, origem=origem, evento_id=lin["evento_id"],
        periodo=lin.get("periodo", ""),
    )
    out.update(extra)
    return out


def _excluido(lin: dict[str, str], cfg: dict[str, Any]) -> str:
    """Motivo da exclusão manual do frame (``exclusoes`` no YAML), ou "".

    Existe para trechos em que o rótulo da estação é verdadeiro para a rua mas
    falso para a imagem: sob viaduto ou dentro de garagem o vidro está
    protegido, a estação continua dizendo garoa e a foto mostra vidro seco.
    """
    hora = _local(lin, cfg["utc_offset_h"]).time()
    for ex in cfg.get("exclusoes") or []:
        if lin["evento_id"] == ex["evento_id"] and _hms(ex["local_desde"]) <= hora <= _hms(ex["local_ate"]):
            return ex["motivo"]
    return ""


def _anexar_sinteticos(linhas, sessoes, sinteticos, particao, cfg) -> None:
    """Anexa sintéticos à ``particao``, exigindo que cada base esteja nela (real)."""
    reais = {
        Path(l["caminho"]).relative_to(cfg["imagens_dir"]).as_posix()
        for l in linhas if l["particao"] == particao and l["origem"] == "real"
    }
    ruins = sorted({s["base_frame"] for s in sinteticos} - reais)
    if ruins:
        raise ValueError(
            f"{len(ruins)} base_frame fora da partição {particao} real, ex.: {ruins[:3]}"
        )
    for s in sinteticos:
        linhas.append({
            "caminho": s["caminho"], "classe": s["classe"], "mm_h": s["mm_h_alvo"],
            "particao": particao, "origem": "sintetico", "evento_id": f"sintetico__{particao}",
            "base_frame": s["base_frame"], "seed": s["seed"],
            "rotulo_fraco": "", "trecho": "", "periodo": "",
        })
    sessoes[f"sinteticos:{particao}"] = {
        "antes_stride": len(sinteticos), "depois_stride": len(sinteticos),
    }


def montar_intensidade(cfg, imt, ircnn, youtube, sinteticos=None, sinteticos_val=None):
    """Retorna (linhas_intensidade, contagens_por_sessao)."""
    linhas: list[dict[str, Any]] = []
    sessoes: dict[str, dict[str, int]] = {}
    for regra in cfg["intensidade"]:
        bruto = _selecionar({**regra, 'stride': False}, imt, cfg)
        sel = _selecionar(regra, imt, cfg)
        chave = f"{regra['evento_id']}:{regra['particao']}"
        sessoes[chave] = {"antes_stride": len(bruto), "depois_stride": len(sel)}
        linhas += [_linha(r, cfg, r["classe"], regra["particao"], "real") for r in sel]

    o = cfg["ordinal_2309"]
    d23 = [
        r for r in imt
        if r["pasta"] == o["pasta"] and _local(r, cfg["utc_offset_h"]).date().isoformat() == o["data_local"]
    ]
    d23.sort(key=lambda r: (_ts(r), r["arquivo"]))
    for r in d23:
        r = dict(r, evento_id=r["evento_id"] or f"{o['pasta']}__{o['data_local']}")
        linhas.append(_linha(r, cfg, "", o["particao"], "real", mm_h="", rotulo_fraco=o["rotulo_fraco"]))
    sessoes[f"{o['pasta']}__{o['data_local']}:{o['particao']}"] = {"antes_stride": len(d23), "depois_stride": len(d23)}

    # Os manifests de irCNN/YouTube gravam caminhos relativos a ml/; aqui ficam relativos à raiz.
    for r in ircnn:
        linhas.append({c: r.get(c, "") for c in COLUNAS} | {"particao": "test_ircnn", "origem": "irCNN", "caminho": _da_raiz(r["caminho"])})
    for r in youtube:
        linhas.append({c: r.get(c, "") for c in COLUNAS} | {"particao": "test_ordinal_youtube", "origem": "youtube", "caminho": _da_raiz(r["caminho"])})

    if sinteticos:
        _anexar_sinteticos(linhas, sessoes, sinteticos, "train", cfg)
    if sinteticos_val:
        _anexar_sinteticos(linhas, sessoes, sinteticos_val, "val", cfg)
    return linhas, sessoes


def montar_gate(cfg, imt):
    linhas: list[dict[str, Any]] = []
    sessoes: dict[str, dict[str, int]] = {}
    for regra in cfg["intensidade"]:  # chuva = mesmas partições do garoa
        sel = _selecionar(regra, imt, cfg)
        for r in sel:
            linhas.append(_linha(r, cfg, "chuva", regra["particao"], "real", mm_h=r["mm_h"]))
    for regra in cfg["gate_seco"]:
        bruto = _selecionar({**regra, 'stride': False}, imt, cfg)
        sel = _selecionar(regra, imt, cfg)
        sessoes[f"{regra['evento_id']}:{regra['particao']}"] = {"antes_stride": len(bruto), "depois_stride": len(sel)}
        linhas += [_linha(r, cfg, "seco", regra["particao"], "real") for r in sel]
    return linhas, sessoes


def resumo(linhas) -> dict[str, dict[str, dict[str, int]]]:
    c = Counter((l["particao"], l["classe"] or "(sem classe)", l["origem"]) for l in linhas)
    out: dict[str, dict[str, dict[str, int]]] = {}
    for (p, cl, o), n in sorted(c.items()):
        out.setdefault(p, {}).setdefault(cl, {})[o] = n
    return out


def _gravar(caminho: Path, linhas) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS)
        w.writeheader()
        w.writerows(linhas)


def verificar_existencia(linhas, raiz: Path) -> None:
    faltando = [l["caminho"] for l in linhas if not (raiz / l["caminho"]).exists()]
    if faltando:
        raise FileNotFoundError(f"{len(faltando)} caminhos inexistentes, ex.: {faltando[:3]}")


def carregar_sinteticos(caminho: Path, raiz: Path) -> list[dict[str, str]] | None:
    """Lê o manifest do gerador; ``caminho`` vira relativo à raiz do repo."""
    if not caminho.exists():
        return None
    out = []
    for r in _ler_csv(caminho):
        if r.get("caminho"):
            rel = r["caminho"]
        else:  # o gerador escreve `arquivo` relativo ao diretório do manifest
            rel = (caminho.parent / r["arquivo"]).relative_to(raiz).as_posix()
        out.append({**r, "caminho": rel})
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=str(RAIZ / "ml/configs/splits_intensidade.yaml"))
    args = ap.parse_args(argv)
    cfg = yaml.safe_load(open(args.config, encoding="utf-8"))
    ent = cfg["entradas"]
    imt_bruto = _ler_csv(RAIZ / ent["imt"])
    excluidos = Counter(m for m in (_excluido(r, cfg) for r in imt_bruto if r["classe"]) if m)
    imt = [r for r in imt_bruto if not _excluido(r, cfg)]
    sint = carregar_sinteticos(RAIZ / ent["sinteticos"], RAIZ)
    sint_val = (
        carregar_sinteticos(RAIZ / ent["sinteticos_val"], RAIZ)
        if ent.get("sinteticos_val") else None
    )
    linhas, sess_i = montar_intensidade(
        cfg, imt, _ler_csv(RAIZ / ent["ircnn"]), _ler_csv(RAIZ / ent["youtube"]), sint,
        sint_val,
    )
    gate, sess_g = montar_gate(cfg, imt)
    verificar_existencia(linhas, RAIZ)
    verificar_existencia(gate, RAIZ)
    _gravar(RAIZ / cfg["saida"]["intensidade"], linhas)
    _gravar(RAIZ / cfg["saida"]["gate"], gate)
    res = {
        "intensidade": resumo(linhas), "gate": resumo(gate),
        "frames_por_sessao": {"intensidade": sess_i, "gate": sess_g},
        "sinteticos_incluidos": sint is not None,
        "sinteticos_val_incluidos": sint_val is not None,
        "excluidos_por_motivo": dict(sorted(excluidos.items())),
        "aviso": None if sint is not None else "manifest de sinteticos ausente: gerado sem sinteticos",
    }
    with open(RAIZ / cfg["saida"]["resumo"], "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())
