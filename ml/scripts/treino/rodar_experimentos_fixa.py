#!/usr/bin/env python3
"""Roteiro único dos experimentos do modelo de câmera fixa (plano C, Task 7; spec CF5).

Junta num comando o que antes eram ~15 passos manuais. Cada etapa pode ser rodada sozinha e é
retomável: um fold já treinado (``metricas.json`` existe e o run é mais novo que o CSV de splits)
não é treinado de novo.

Uso (sempre da raiz ``CityRain/``):
    python ml/scripts/treino/rodar_experimentos_fixa.py checar        # ambiente, dados e splits
    python ml/scripts/treino/rodar_experimentos_fixa.py splits        # monta ml/data/splits/fixa_v1.csv
    python ml/scripts/treino/rodar_experimentos_fixa.py f0            # v3 do carro nas câmeras fixas
    python ml/scripts/treino/rodar_experimentos_fixa.py cv f1 f2 f3   # CV por evento do irCNN, 4 folds cada
    python ml/scripts/treino/rodar_experimentos_fixa.py escolher      # aplica o critério CF5
    python ml/scripts/treino/rodar_experimentos_fixa.py tudo          # checar -> splits -> f0 -> cv -> escolher
    python ml/scripts/treino/rodar_experimentos_fixa.py final         # treina o vencedor e exporta o ONNX

``final`` usa o vencedor gravado por ``escolher`` (ou ``final f1|f2|f3`` para forçar). Ele NÃO roda
dentro de ``tudo``: a escolha é registrada e conferida por uma pessoa antes.
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[3]
PY = sys.executable
CONFIGS = {
    "f1": RAIZ / "ml/configs/treino_fixa_f1_mnv3.yaml",
    "f2": RAIZ / "ml/configs/treino_fixa_f2_effb0.yaml",
    "f3": RAIZ / "ml/configs/treino_fixa_f3_mnv3_ref.yaml",
}
SPLITS_CFG = RAIZ / "ml/configs/splits_fixa_v1.yaml"
RUNS = RAIZ / "ml/runs"
RESULTADOS = RAIZ / "ml/resultados"
ESCOLHA = RESULTADOS / "fixa_escolha.json"
FINAL_CFG = RAIZ / "ml/configs/treino_fixa_final.yaml"

# CF5: limiares fixados na spec antes de olhar os resultados
MIN_RECALL_FORTE = 0.7
MIN_CHUVA_SECO = 0.8


def _rodar(args: list[object]) -> None:
    """Roda um passo; no Mac, com caffeinate para o sistema não dormir no meio do treino."""
    cmd = [PY, *map(str, args)]
    if platform.system() == "Darwin" and shutil.which("caffeinate"):
        cmd = ["caffeinate", "-i", *cmd]
    print(f"\n$ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, cwd=RAIZ, check=True)


def _rel(p: Path) -> str:
    """Caminho relativo à raiz quando possível (só para mensagens)."""
    try:
        return str(p.relative_to(RAIZ))
    except ValueError:
        return str(p)


def _cfg_splits() -> dict:
    return yaml.safe_load(SPLITS_CFG.read_text())


def _splits_csv() -> Path:
    return RAIZ / _cfg_splits()["saida"]


# ---------------------------------------------------------------- checar

def checar(estrito: bool = True) -> bool:
    ok = True

    def falha(msg: str) -> None:
        nonlocal ok
        ok = False
        print(f"  [FALHA] {msg}")

    print("== ambiente")
    v = sys.version_info
    print(f"  python {v.major}.{v.minor}.{v.micro} ({PY})")
    if v < (3, 10):
        falha("precisa de Python >= 3.10 (recomendado 3.11)")
    for mod in ("torch", "torchvision", "onnx", "onnxruntime", "onnxscript", "pandas", "sklearn", "scipy", "PIL", "yaml"):
        try:
            importlib.import_module(mod)
        except ImportError:
            falha(f"falta o pacote {mod}: python -m pip install -r ml/requirements-treino.txt")
    try:
        import torch
        disp = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        print(f"  torch {torch.__version__}, dispositivo {disp}")
        if disp == "cpu":
            print("  [aviso] sem GPU: cada fold leva horas. Preferir Mac M-series ou NVIDIA.")
    except ImportError:
        pass

    print("== dados")
    cfg = _cfg_splits()
    raw = RAIZ / cfg["raiz_frames_lives"]
    n_raw = sum(1 for _ in raw.rglob("*.jpg")) if raw.is_dir() else 0
    print(f"  {_rel(raw)}: {n_raw} jpg")
    if n_raw == 0:
        falha("frames das lives ausentes: descompactar o pacote de dados (docs/GUIA-TREINO-EQUIPE.md)")
    ircnn = RAIZ / "ml/data/processed/ircnn"
    n_ir = sum(1 for _ in ircnn.rglob("*.jpg")) if ircnn.is_dir() else 0
    print(f"  ml/data/processed/ircnn: {n_ir} jpg")
    if n_ir == 0:
        falha("irCNN ausente: descompactar o pacote de dados")
    for chave in ("manifest_lives", "manifest_lives_5km", "manifest_ircnn", "revisao_csv"):
        p = RAIZ / cfg[chave]
        if not p.is_file():
            falha(f"{chave} ausente: {cfg[chave]}")
    rev = RAIZ / cfg["revisao_csv"]
    if rev.is_file():
        with open(rev, newline="") as f:
            linhas = list(csv.DictReader(f))
        marcadas = sum(1 for r in linhas if (r.get("excluir") or "").strip())
        print(f"  revisao.csv: {len(linhas)} linhas, {marcadas} com excluir preenchido")
        if not (RAIZ / "ml/data/review/camera_fixa/REVISADO.txt").is_file():
            print("  [aviso] revisão visual dos painéis não registrada (criar ml/data/review/camera_fixa/REVISADO.txt "
                  "com nome e data depois de revisar). Moderada/forte a 5 km só valem revisados (CF3.2).")
    cams = yaml.safe_load((RAIZ / cfg["coleta_fixa_config"]).read_text())
    for fonte in cams.get("fontes", []):
        if fonte.get("ativa", True) and fonte.get("tipo") == "youtube" and not fonte.get("posicao_verificada"):
            print(f"  [aviso] {fonte['id']} sem posicao_verificada: fica fora dos splits")

    print("== splits")
    csv_splits = _splits_csv()
    resumo = RAIZ / cfg["resumo"]
    if not csv_splits.is_file():
        msg = "splits ainda não montados: rodar a etapa `splits`"
        falha(msg) if estrito else print(f"  [aviso] {msg}")
    else:
        with open(csv_splits, newline="") as f:
            linhas = list(csv.DictReader(f))
        faltando = [r["caminho"] for r in linhas if not (RAIZ / r["caminho"]).is_file()
                    and not (RAIZ / "ml" / r["caminho"]).is_file()]
        print(f"  {_rel(csv_splits)}: {len(linhas)} linhas, {len(faltando)} imagens não encontradas")
        if faltando:
            falha(f"imagens do split ausentes (ex.: {faltando[:2]}); dados incompletos ou de outra versão")
        if resumo.is_file():
            r = json.loads(resumo.read_text())
            if r.get("referencias_faltando"):
                falha(f"câmeras sem frame seco de referência: {r['referencias_faltando']} "
                      "(todas as linhas delas saem dos modelos; colher seco no DVR)")
            print(f"  por partição/classe: {json.dumps(r.get('por_particao_classe'), ensure_ascii=False)}")
    agora = datetime.now(timezone.utc)
    cong = datetime.fromisoformat(cfg["congelamento_utc"].replace("Z", "+00:00"))
    if agora < cong:
        print(f"  [aviso] antes do congelamento ({cfg['congelamento_utc']}): o teste prospectivo ainda está vazio. "
              "Splits definitivos só a partir de 13/10.")
    print("\n" + ("[ok] pronto para treinar" if ok else "[FALHA] corrigir os itens acima antes de treinar"))
    return ok


# ---------------------------------------------------------------- etapas

def splits() -> None:
    # Splits idênticos aos anteriores mantêm a data do arquivo: os folds já treinados continuam
    # valendo (_run_pronto compara com essa data) e `tudo` pode ser rodado de novo depois de cair.
    csv_splits = _splits_csv()
    antes = (csv_splits.read_bytes(), csv_splits.stat()) if csv_splits.is_file() else None
    _rodar([RAIZ / "ml/scripts/dataset/montar_splits_fixa.py", "--config", SPLITS_CFG])
    if antes and csv_splits.read_bytes() == antes[0]:
        os.utime(csv_splits, ns=(antes[1].st_atime_ns, antes[1].st_mtime_ns))
        print("[splits] iguais aos anteriores: folds já treinados continuam valendo")
    elif antes:
        print("[splits] mudaram: folds anteriores serão treinados de novo")
    r = json.loads((RAIZ / _cfg_splits()["resumo"]).read_text())
    if r.get("referencias_faltando"):
        sys.exit(f"[FALHA] câmeras sem referência seca: {r['referencias_faltando']}")


def f0() -> None:
    _rodar([RAIZ / "ml/scripts/avaliacao/avaliar_v3_em_fixa.py"])


def _nome(exp: str) -> str:
    return yaml.safe_load(CONFIGS[exp].read_text())["nome"]


def _n_folds(exp: str) -> int:
    return len(yaml.safe_load(CONFIGS[exp].read_text())["dados"]["ircnn_cv"]["folds"])


def _run_pronto(exp: str, k: int) -> Path | None:
    """Run mais recente do fold k que terminou e é posterior aos splits atuais."""
    limite = _splits_csv().stat().st_mtime
    feitos = [p for p in RUNS.glob(f"{_nome(exp)}_fold{k}__*")
              if (p / "metricas.json").is_file() and p.stat().st_mtime >= limite]
    return max(feitos, key=lambda p: p.name) if feitos else None


def _cv_recente(exp: str) -> Path | None:
    cvs = [p for p in RUNS.glob(f"{_nome(exp)}__cv_*") if (p / "metricas_cv.json").is_file()]
    return max(cvs, key=lambda p: p.name) if cvs else None


def cv(exps: list[str]) -> None:
    sys.path.insert(0, str(RAIZ / "ml/src"))
    from cityrain_ml.training.fixa import agregar_cv_fixa

    for exp in exps:
        runs = []
        for k in range(_n_folds(exp)):
            run = _run_pronto(exp, k)
            if run:
                print(f"[{exp}] fold {k}: já feito em {run.name}")
            else:
                print(f"\n===== {exp} fold {k} =====")
                _rodar([RAIZ / "ml/scripts/treino/treinar_fixa.py", CONFIGS[exp], "--fold", k])
                run = _run_pronto(exp, k)
                if run is None:
                    sys.exit(f"[FALHA] {exp} fold {k} terminou sem metricas.json")
            runs.append(run)
        if exp == "f3":
            # ablação do atalho de câmera: mesma avaliação com a referência de outra câmera
            for run in runs:
                if not list(run.glob("metricas_avaliacao_*_ref_trocada.json")):
                    _rodar([RAIZ / "ml/scripts/treino/treinar_fixa.py", CONFIGS[exp], "--avaliar",
                            run / "melhor.pt", "--referencia-trocada"])
        destino = RUNS / f"{_nome(exp)}__cv_{datetime.now():%Y%m%d_%H%M%S}"
        met = agregar_cv_fixa(runs, destino)
        r = met["test_ircnn_agregado"]
        print(f"[{exp}] CV em {_rel(destino)}: irCNN F1 macro {r['resumo']['f1_macro']:.3f}")


# ---------------------------------------------------------------- escolha (CF5)

def _resumo_exp(exp: str) -> dict | None:
    cvdir = _cv_recente(exp)
    if cvdir is None:
        return None
    met = json.loads((cvdir / "metricas_cv.json").read_text())
    runs = [RUNS / n for n in met["folds"]]
    folds = [json.loads((r / "metricas.json").read_text()) for r in runs]
    spear = [f["particoes"]["test_camera"].get("spearman_score_mm_h") for f in folds
             if f["particoes"]["test_camera"].get("n", 0)]
    spear = [s for s in spear if s is not None]
    ir = met["test_ircnn_agregado"]
    cam = met["test_camera"]
    boot = met.get("bootstrap_ircnn") or {}
    res = {
        "exp": exp, "cv": cvdir.name,
        "f1_ircnn": ir["resumo"]["f1_macro"],
        "f1_ircnn_ic95": (boot.get("f1_macro") or {}).get("ic95"),
        "recall_forte_ircnn": ir.get("recall_forte"),
        "chuva_seco_camera": (cam.get("acuracia_chuva_vs_seco") or {}).get("media"),
        "f1_camera": (cam.get("resumo.f1_macro") or {}).get("media"),
        "spearman_camera": statistics.mean(spear) if spear else None,
        "epocas_cv": [f["checkpoint_epoca"] for f in folds],
        "parametros": _parametros(exp),
    }
    if exp == "f3":
        trocadas = []
        for r in runs:
            arqs = sorted(r.glob("metricas_avaliacao_*_ref_trocada.json"))
            if arqs:
                p = json.loads(arqs[-1].read_text())["particoes"]["test_ircnn"]
                if p.get("n", 0):
                    trocadas.append(p["resumo"]["f1_macro"])
        normais = [f["particoes"]["test_ircnn"]["resumo"]["f1_macro"] for f in folds
                   if f["particoes"]["test_ircnn"].get("n", 0)]
        if trocadas and normais:
            res["f3_ablacao"] = {"f1_ircnn_normal_media_folds": statistics.mean(normais),
                                 "f1_ircnn_ref_trocada_media_folds": statistics.mean(trocadas)}
    res["passa_cf5"] = bool(
        (res["recall_forte_ircnn"] or 0) >= MIN_RECALL_FORTE
        and (res["chuva_seco_camera"] or 0) >= MIN_CHUVA_SECO
        and (res["spearman_camera"] or 0) > 0)
    return res


def _parametros(exp: str) -> int:
    sys.path.insert(0, str(RAIZ / "ml/src"))
    from cityrain_ml.models.fabrica import construir

    cfg = yaml.safe_load(CONFIGS[exp].read_text())
    canais = 6 if cfg["dados"].get("com_referencia") else 3
    m = construir(cfg["modelo"]["arquitetura"], 4, pretreinado=False, canais_entrada=canais)
    return sum(p.numel() for p in m.parameters())


def _comparar(a: str, b: str) -> dict:
    sys.path.insert(0, str(RAIZ / "ml/scripts/avaliacao"))
    from comparar_fixa import comparar, resolver_runs, salvar

    r = comparar(resolver_runs([_cv_recente(a)]), resolver_runs([_cv_recente(b)]))
    salvar(r, _nome(a), _nome(b), RESULTADOS)
    return r


def escolher() -> dict:
    resumos = [r for r in (_resumo_exp(e) for e in CONFIGS) if r]
    if not resumos:
        sys.exit("[FALHA] nenhuma CV encontrada: rodar a etapa `cv` antes")
    print("\n| Exp | F1 irCNN (IC95) | recall forte irCNN | chuva×seco BC | Spearman BC | parâmetros | CF5 |")
    print("|---|---|---|---|---|---|---|")
    for r in resumos:
        ic = r["f1_ircnn_ic95"]
        ic_txt = f" [{ic[0]:.3f}, {ic[1]:.3f}]" if ic else ""
        fmt = lambda v: "—" if v is None else f"{v:.3f}"  # noqa: E731
        print(f"| {r['exp'].upper()} | {r['f1_ircnn']:.3f}{ic_txt} | {fmt(r['recall_forte_ircnn'])} | "
              f"{fmt(r['chuva_seco_camera'])} | {fmt(r['spearman_camera'])} | {r['parametros'] / 1e6:.2f} M | "
              f"{'passa' if r['passa_cf5'] else 'não passa'} |")

    candidatos = [r for r in resumos if r["passa_cf5"]]
    atingiu = bool(candidatos)
    if not atingiu:
        print("\n[aviso] nenhum experimento atingiu todos os limiares da CF5; escolhendo pelo maior F1 do irCNN "
              "e registrando que o critério não foi atingido (declarar no texto).")
        candidatos = resumos
    lider = max(candidatos, key=lambda r: r["f1_ircnn"])
    empates = []
    for r in candidatos:
        if r is lider:
            continue
        d = _comparar(lider["exp"], r["exp"])["diferenca_f1_macro"]
        print(f"  {lider['exp']} - {r['exp']}: F1 {d['media']:+.3f} IC95 [{d['ic95'][0]:+.3f}, {d['ic95'][1]:+.3f}]")
        if d["ic95"][0] <= 0 <= d["ic95"][1]:
            empates.append(r)
    # empate estatístico -> modelo menor; sem referência (3 canais) desempata parâmetros iguais
    vencedor = min([lider, *empates], key=lambda r: (r["parametros"], r["exp"] == "f3"))
    escolha = {"vencedor": vencedor["exp"], "criterio_cf5_atingido": atingiu,
               "empatados_com_lider": [r["exp"] for r in empates], "lider_por_f1": lider["exp"],
               "epocas_final": int(statistics.median(vencedor["epocas_cv"])),
               "resumos": resumos, "em": datetime.now().isoformat(timespec="seconds")}
    RESULTADOS.mkdir(parents=True, exist_ok=True)
    ESCOLHA.write_text(json.dumps(escolha, indent=2, ensure_ascii=False, default=float))
    print(f"\n[ok] vencedor {vencedor['exp'].upper()} (épocas do final = {escolha['epocas_final']}); "
          f"gravado em {_rel(ESCOLHA)}")
    if "f3_ablacao" in next((r for r in resumos if r["exp"] == "f3"), {}):
        ab = next(r for r in resumos if r["exp"] == "f3")["f3_ablacao"]
        print(f"  F3 referência trocada: F1 irCNN {ab['f1_ircnn_normal_media_folds']:.3f} -> "
              f"{ab['f1_ircnn_ref_trocada_media_folds']:.3f}")
    print("Copiar a tabela acima para docs/resultados-experimentos.md, seção \"Câmera fixa\", e conferir antes do `final`.")
    return escolha


# ---------------------------------------------------------------- final

def final(exp: str | None) -> None:
    if exp is None:
        if not ESCOLHA.is_file():
            sys.exit("[FALHA] sem escolha gravada: rodar `escolher` ou passar f1|f2|f3")
        escolha = json.loads(ESCOLHA.read_text())
        exp, epocas = escolha["vencedor"], escolha["epocas_final"]
    else:
        r = _resumo_exp(exp)
        if r is None:
            sys.exit(f"[FALHA] sem CV de {exp}: a quantidade de épocas sai da mediana da CV")
        epocas = int(statistics.median(r["epocas_cv"]))
    cfg = yaml.safe_load(CONFIGS[exp].read_text())
    cfg["nome"] = f"fixa_final_{exp}"
    cfg["treino"]["epocas"] = epocas
    cfg["treino"]["sem_selecao_por_val"] = True
    FINAL_CFG.write_text(f"# Modelo final da câmera fixa: {exp.upper()} com épocas = mediana da CV "
                         f"(gerado por rodar_experimentos_fixa.py em {datetime.now():%d/%m/%Y})\n"
                         + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))
    _rodar([RAIZ / "ml/scripts/treino/treinar_fixa.py", FINAL_CFG, "--fold", "final"])
    run = max(RUNS.glob("fixa_final_*_foldfinal__*"), key=lambda p: p.name)
    _rodar([RAIZ / "ml/scripts/treino/exportar_onnx_fixa.py", run / "melhor.pt"])
    print(f"\n[ok] modelo final em {_rel(run)} e ONNX em backend/app/inference/modelos/intensidade_fixa.onnx")
    print("Próximo: commitar o ONNX, backend/app/inference/referencias (se F3), ml/configs/treino_fixa_final.yaml, "
          "ml/resultados e abrir PR; pedir o deploy ao Moreno.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("etapa", choices=("checar", "splits", "f0", "cv", "escolher", "tudo", "final"))
    ap.add_argument("exps", nargs="*", help="cv: f1 f2 f3 (padrão: todos); final: f1|f2|f3 (padrão: o escolhido)")
    args = ap.parse_args()
    if any(e not in CONFIGS for e in args.exps):
        ap.error(f"experimentos válidos: {', '.join(CONFIGS)}")
    if args.etapa == "checar":
        sys.exit(0 if checar(estrito=False) else 1)
    if args.etapa == "splits":
        splits()
    elif args.etapa == "f0":
        f0()
    elif args.etapa == "cv":
        cv(args.exps or list(CONFIGS))
    elif args.etapa == "escolher":
        escolher()
    elif args.etapa == "final":
        final(args.exps[0] if args.exps else None)
    elif args.etapa == "tudo":
        if not checar(estrito=False):
            sys.exit(1)
        splits()
        if not checar(estrito=True):
            sys.exit(1)
        f0()
        cv(args.exps or list(CONFIGS))
        escolher()


if __name__ == "__main__":
    main()
